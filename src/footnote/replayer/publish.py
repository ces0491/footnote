"""Publishing a run's messages to the feed hub, partitioned by run so they stay in order."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from azure.eventhub import EventData
from azure.eventhub.aio import EventHubProducerClient

from footnote.live.contract import KIND_FEED, PROP_BACKFILL, PROP_KIND, PROP_PUBLISHED_AT, PROP_RUN_ID


@dataclass(frozen=True)
class Envelope:
    body: dict
    kind: str = KIND_FEED
    backfill: bool = False


class Publisher(Protocol):
    async def send(self, run_id: str, envelopes: list[Envelope]) -> None:
        """Publish in order; returns once the hub has accepted them."""
        ...


def to_event(run_id: str, envelope: Envelope, published_at: datetime | None = None) -> EventData:
    event = EventData(json.dumps(envelope.body, separators=(",", ":"), ensure_ascii=False))
    event.properties = {
        PROP_RUN_ID: run_id,
        PROP_KIND: envelope.kind,
        # A datetime travels as an AMQP timestamp (64-bit milliseconds); a Python int would be encoded
        # as a 32-bit AMQP int, which epoch milliseconds overflow.
        PROP_PUBLISHED_AT: published_at or datetime.now(UTC),
        PROP_BACKFILL: envelope.backfill,
    }
    return event


class EventHubPublisher:
    def __init__(self, producer: EventHubProducerClient) -> None:
        self.producer = producer

    async def send(self, run_id: str, envelopes: list[Envelope]) -> None:
        batch = await self.producer.create_batch(partition_key=run_id)
        for envelope in envelopes:
            event = to_event(run_id, envelope)
            try:
                batch.add(event)
            except ValueError:
                if not len(batch):
                    raise  # the event alone doesn't fit, or can't be encoded
                await self.producer.send_batch(batch)  # the batch is full
                batch = await self.producer.create_batch(partition_key=run_id)
                batch.add(event)
        if len(batch):
            await self.producer.send_batch(batch)
