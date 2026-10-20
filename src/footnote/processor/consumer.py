"""Reading the feed hub: decode each event, hand the batch to the Processor, then checkpoint.

Checkpoints live in Blob Storage, so a restarted processor resumes where it stopped and a second
replica would share partitions instead of reading them twice. A partition with no checkpoint yet is
read from a few minutes before this processor started, so a replay that began while a new revision
was coming up isn't lost. Processing is idempotent, so reading those minutes again is harmless.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from azure.eventhub import EventData
from azure.eventhub.aio import EventHubConsumerClient, PartitionContext

from footnote.live.contract import KIND_FEED, PROP_BACKFILL, PROP_KIND, PROP_PUBLISHED_AT, PROP_RUN_ID
from footnote.processor.core import Incoming, Processor

log = logging.getLogger(__name__)

# How far back to read a partition that has no checkpoint.
UNCHECKPOINTED_LOOKBACK = timedelta(minutes=5)


def _text(value: Any) -> Any:
    return value.decode("utf-8") if isinstance(value, bytes) else value


def _epoch_ms(value: Any) -> int:
    """An AMQP timestamp arrives as epoch milliseconds; accept a datetime too."""
    return int(value.timestamp() * 1000) if isinstance(value, datetime) else int(value)


def decode(event: EventData) -> Incoming:
    props = {_text(k): _text(v) for k, v in (event.properties or {}).items()}
    enqueued = event.enqueued_time
    body = json.loads(event.body_as_str(encoding="UTF-8"))
    if not isinstance(body, dict):
        raise ValueError(f"the body is a JSON {type(body).__name__}, not an object")
    return Incoming(
        run_id=str(props[PROP_RUN_ID]),
        kind=str(props.get(PROP_KIND, KIND_FEED)),
        body=body,
        published_at=_epoch_ms(props[PROP_PUBLISHED_AT]),
        enqueued_at=_epoch_ms(enqueued) if enqueued else None,
        backfill=bool(props.get(PROP_BACKFILL, False)),
    )


def decode_batch(events: list[EventData], partition: str) -> list[Incoming]:
    """The batch decoded. An event that can't be is logged and left out: read again it would fail
    the same way, and the partition would never get past it."""
    decoded = []
    for event in events:
        try:
            decoded.append(decode(event))
        except Exception:
            log.exception(
                "feed hub (%s): skipping event %s, which isn't a replayer message", partition, event.sequence_number
            )
    return decoded


async def consume(client: EventHubConsumerClient, processor: Processor) -> None:
    """Receive until the client is closed."""

    async def on_batch(context: PartitionContext, events: list[EventData]) -> None:
        if not events:
            return
        if decoded := decode_batch(events, context.partition_id):
            await processor.handle(decoded)
        await context.update_checkpoint(events[-1])

    async def on_error(context: PartitionContext | None, error: Exception) -> None:
        partition = context.partition_id if context else "load balancing"
        log.error("feed hub error (%s): %r", partition, error)

    await client.receive_batch(
        on_batch,
        max_batch_size=200,
        prefetch=300,
        starting_position=datetime.now(UTC) - UNCHECKPOINTED_LOOKBACK,
        starting_position_inclusive=True,
        on_error=on_error,
    )
