"""Pushing to a run's viewers through Web PubSub, one group per run."""

from __future__ import annotations

from azure.messaging.webpubsubservice.aio import WebPubSubServiceClient

from footnote.live.contract import group_name


class WebPubSubPush:
    def __init__(self, client: WebPubSubServiceClient) -> None:
        self.client = client

    async def send(self, run_id: str, message: dict) -> None:
        # Sent as JSON, so clients receive it parsed. The SDK serialises it with json.dumps defaults.
        await self.client.send_to_group(group_name(run_id), message, content_type="application/json")
