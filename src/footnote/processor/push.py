"""Pushing to a run's viewers through Web PubSub, one group per run."""

from __future__ import annotations

from azure.messaging.webpubsubservice.aio import WebPubSubServiceClient

from footnote.live.contract import group_name, wire

# How long the agents service waits on a push before going on without it: a push once hung for a
# minute on a TLS handshake with Web PubSub. What a push carries is stored before it is sent, and a
# page that misses one notices the gap in revisions and fetches the snapshot. It also keeps the
# producer's answer inside the web app's 10 s wait on the desk (frontend/src/lib/server/desk.ts).
PUSH_SECONDS = 5.0


class WebPubSubPush:
    def __init__(self, client: WebPubSubServiceClient) -> None:
        self.client = client

    async def send(self, run_id: str, message: dict) -> None:
        # As text: the SDK serialises a JSON payload with json.dumps defaults, which put a space after
        # every comma and colon. Clients parse it (frontend/src/hooks/use-live-run.ts).
        await self.client.send_to_group(group_name(run_id), wire(message), content_type="text/plain")
