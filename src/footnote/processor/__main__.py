"""Run the processor: python -m footnote.processor.

Settings come from the environment (set by infra/processor.bicep in Azure):

    EVENTHUB_NAMESPACE, EVENTHUB_NAME     the feed hub (fully qualified namespace)
    CHECKPOINT_BLOB_URL, CHECKPOINT_CONTAINER
    WEBPUBSUB_ENDPOINT, WEBPUBSUB_HUB
    POSTGRES_HOST, POSTGRES_DATABASE, POSTGRES_USER
    WEB_DB_ROLE, WEB_DB_OBJECT_ID         the web app's identity, granted read access at start-up
    AZURE_CLIENT_ID                       the processor's managed identity
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import sys

from azure.eventhub.aio import EventHubConsumerClient
from azure.eventhub.extensions.checkpointstoreblobaio import BlobCheckpointStore
from azure.messaging.webpubsubservice.aio import WebPubSubServiceClient

from footnote import cloud
from footnote.db.connect import entra_pool
from footnote.db.migrate import ensure_web_role, migrate
from footnote.live.analysis import Analysis
from footnote.live.match import SHOWCASE_MATCH_ID, load_match
from footnote.processor.consumer import consume
from footnote.processor.core import OVERDUE_MS, Processor
from footnote.processor.push import WebPubSubPush
from footnote.processor.store import PostgresStore

log = logging.getLogger("footnote.processor")

SWEEP_INTERVAL = 60.0  # seconds between looks for runs left running by a crashed replayer


async def sweep(processor: Processor) -> None:
    """End abandoned runs, once a minute.

    The first look waits until a restarted processor has caught up on the hub: until then, a healthy
    run's stored state is behind and its next message can look overdue.
    """
    await asyncio.sleep(OVERDUE_MS / 1000)
    while True:
        try:
            await processor.end_overdue()
        except Exception:
            log.exception("looking for abandoned runs failed")
        await asyncio.sleep(SWEEP_INTERVAL)


async def main() -> None:
    match = load_match(os.environ.get("FOOTNOTE_MATCH_ID", SHOWCASE_MATCH_ID))
    # The tracking and the fitted models, shared by every run of the match.
    analysis = Analysis.load(match)
    credential = cloud.credential()
    pool = entra_pool(credential)
    await pool.open(wait=True, timeout=120)
    applied = await migrate(pool)
    log.info("migrations applied: %s", applied or "none pending")
    web_role, web_object_id = os.environ.get("WEB_DB_ROLE"), os.environ.get("WEB_DB_OBJECT_ID")
    if web_role and web_object_id:
        await ensure_web_role(credential, pool, web_role, web_object_id)
    store = PostgresStore(pool)
    await store.put_match(match.meta)

    webpubsub = WebPubSubServiceClient(
        endpoint=cloud.require("WEBPUBSUB_ENDPOINT"), hub=cloud.require("WEBPUBSUB_HUB"), credential=credential
    )
    checkpoints = BlobCheckpointStore(
        blob_account_url=cloud.require("CHECKPOINT_BLOB_URL"),
        container_name=cloud.require("CHECKPOINT_CONTAINER"),
        credential=credential,
    )
    consumer = EventHubConsumerClient(
        fully_qualified_namespace=cloud.require("EVENTHUB_NAMESPACE"),
        eventhub_name=cloud.require("EVENTHUB_NAME"),
        consumer_group="$Default",
        credential=credential,
        checkpoint_store=checkpoints,
        # Claim partitions quickly after a restart or a new revision; the defaults wait minutes. Each
        # cycle is a few blob operations, so the cost of checking often is negligible.
        load_balancing_interval=5,
        partition_ownership_expiration_interval=15,
    )
    processor = Processor(match, store, WebPubSubPush(webpubsub), analysis=analysis)

    if sys.platform != "win32":
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.ensure_future(consumer.close()))

    log.info("processing %s from %s", match.match_id, cloud.require("EVENTHUB_NAME"))
    try:
        async with consumer, webpubsub:
            sweeper = asyncio.create_task(sweep(processor), name="sweep")
            try:
                await consume(consumer, processor)
            finally:
                sweeper.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await sweeper
    finally:
        await pool.close()
        await credential.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("azure").setLevel(logging.WARNING)
    asyncio.run(main())
