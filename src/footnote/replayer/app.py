"""The replayer's HTTP API. Reachable only inside the Container Apps environment; the web app calls it.

POST   /runs            start a replay: {"start_minute": 1-90, "speed": 1, 2 or 4, "viewer": optional ID,
                        "producer": "auto" or "manual"}; returns the run descriptor. A viewer's new
                        replay replaces their previous one
GET    /runs            the runs in progress
GET    /runs/{run_id}   one run's descriptor
DELETE /runs/{run_id}   stop a run: {"viewer": ID}, which must be the one that started it, if any
GET    /healthz
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from azure.eventhub.aio import EventHubProducerClient
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from footnote import cloud
from footnote.generator.schema import validate_message
from footnote.live.contract import VIEWER_PATTERN
from footnote.live.match import SHOWCASE_MATCH_ID, Match, load_match
from footnote.live.timeline import Timeline
from footnote.replayer.publish import EventHubPublisher, Publisher
from footnote.replayer.runs import RunManager

log = logging.getLogger(__name__)


class StartRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_minute: int = Field(default=1, ge=1, le=90, description="Broadcast minute to jump to")
    speed: Literal[1, 2, 4] = Field(default=1, description="Replay speed")
    viewer: str | None = Field(
        default=None,
        pattern=VIEWER_PATTERN,
        description="The anonymous ID of the browser starting it; its previous replay is stopped",
    )
    producer: Literal["auto", "manual"] = Field(
        default="auto", description="Approve each graphic as it is found, or leave it for the producer"
    )


class StopRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    viewer: str | None = Field(
        default=None,
        pattern=VIEWER_PATTERN,
        description="The anonymous ID of the browser asking; a run started with one stops only for it",
    )


def create_app(match: Match | None = None, publisher: Publisher | None = None) -> FastAPI:
    """The app; tests pass a match and a publisher, production builds both from the environment."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        loaded = match or load_match(os.environ.get("FOOTNOTE_MATCH_ID", SHOWCASE_MATCH_ID))
        for message in loaded.feed:
            validate_message(message)  # refuse to replay a feed that breaks the contract
        timeline = Timeline.from_feed(loaded.feed)
        if publisher is not None:
            app.state.runs = RunManager(loaded, timeline, publisher)
            yield
            await app.state.runs.close()
            return
        credential = cloud.credential()
        producer = EventHubProducerClient(
            fully_qualified_namespace=cloud.require("EVENTHUB_NAMESPACE"),
            eventhub_name=cloud.require("EVENTHUB_NAME"),
            credential=credential,
        )
        async with producer:
            app.state.runs = RunManager(loaded, timeline, EventHubPublisher(producer))
            log.info("replaying %s into %s", loaded.match_id, cloud.require("EVENTHUB_NAME"))
            yield
            await app.state.runs.close()
        await credential.close()

    app = FastAPI(title="Footnote replayer", lifespan=lifespan)

    def manager(request: Request) -> RunManager:
        runs: RunManager = request.app.state.runs
        return runs

    @app.post("/runs", status_code=201)
    async def start_run(body: StartRun, request: Request) -> dict:
        return await manager(request).start(
            body.start_minute, float(body.speed), viewer=body.viewer, producer=body.producer
        )

    @app.get("/runs")
    async def list_runs(request: Request) -> list[dict]:
        return [r.descriptor for r in manager(request).runs.values()]

    @app.get("/runs/{run_id}")
    async def get_run(run_id: str, request: Request) -> dict:
        run = manager(request).runs.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="no such run in progress")
        return run.descriptor

    @app.delete("/runs/{run_id}", status_code=204)
    async def stop_run(run_id: str, request: Request, body: StopRun | None = None) -> Response:
        # Only the viewer who started a replay may stop it, as only they may produce it; a run
        # started without a viewer belongs to nobody, and anyone may stop it.
        run = manager(request).runs.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="no such run in progress")
        if run.viewer is not None and (body is None or body.viewer != run.viewer):
            raise HTTPException(status_code=403, detail="only the viewer who started this replay can stop it")
        if not await manager(request).stop(run_id):
            raise HTTPException(status_code=404, detail="no such run in progress")
        return Response(status_code=204)

    @app.get("/healthz")
    async def healthz(request: Request) -> dict:
        return {"status": "ok", "runs": len(manager(request).runs)}

    return app
