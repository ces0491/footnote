"""Pushing to a run's viewers through Web PubSub, one group per run."""

from __future__ import annotations

from azure.messaging.webpubsubservice.aio import WebPubSubServiceClient

from footnote.live.contract import group_name, wire


class WebPubSubPush:
    def __init__(self, client: WebPubSubServiceClient) -> None:
        self.client = client

    async def send(self, run_id: str, message: dict) -> None:
        # As text: the SDK serialises a JSON payload with json.dumps defaults, which put a space after
        # every comma and colon. Clients parse it (frontend/src/hooks/use-live-run.ts).
        await self.client.send_to_group(group_name(run_id), wire(message), content_type="text/plain")
