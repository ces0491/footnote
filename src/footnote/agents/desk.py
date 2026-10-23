"""The producer's desk: what a producer does to a run's graphics, and the checks it applies.

The web app's producer console calls it over the Container Apps environment's internal network,
passing the anonymous ID of the viewer acting. Only the viewer who started a replay may produce it,
and only while it runs. Each action changes one insight, or how the run's graphics are approved,
and an insight change bumps the run's insight revision in the same transaction and is pushed to the
run's viewers, like every other change to an insight (footnote.db.insights).

    approve   a drafted, killed or withdrawn graphic may air, once no agent is drafting it
    kill      a drafted graphic never airs
    withdraw  an approved graphic comes off air
    redraft   an agent drafts the card again, past the cache of earlier replays; the desk refuses a
              redraft of a graphic on air with wording the producer approved until the producer
              withdraws it, and each card and each replay has a limit
    edit      the producer's own wording, written as a draft with placeholders for the figures; it
              passes the same checks as an agent's draft (insights/draft.py), against the moment's
              facts and the events its card already links to, is never cached for other replays,
              and each card and each replay has a limit
    mode      approve each graphic automatically as it is found, or leave it to the producer

A run starts in the mode its viewer chose; switching applies to the insights found from then on.
What a producer approves is the wording they saw: an agent's draft can't land on a graphic they
approved, because approving waits for a draft in flight and a redraft needs the graphic off air.

POST /runs/{run_id}/producer                    {"viewer": ID, "mode": "auto" | "manual"}
POST /runs/{run_id}/insights/{insight_id}       {"viewer": ID, "action": ..., "draft": for an edit}
GET  /healthz
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal, Protocol

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from footnote.db.connect import Pool
from footnote.db.insights import AGENT_CHANNEL, Connection, next_rev, push_insights
from footnote.insights.draft import Draft, check, limits_for, render
from footnote.insights.facts import facts_from_json
from footnote.live.contract import VIEWER_PATTERN
from footnote.processor.push import PUSH_SECONDS

log = logging.getLogger(__name__)

Action = Literal["approve", "kill", "withdraw", "redraft", "edit"]

# The statuses each action may start from.
_FROM: dict[str, frozenset[str]] = {
    "approve": frozenset({"drafted", "killed", "withdrawn"}),
    "kill": frozenset({"drafted"}),
    "withdraw": frozenset({"approved"}),
}
_TO = {"approve": "approved", "kill": "killed", "withdraw": "withdrawn"}
_REFUSED = {
    "approve": "It is approved already.",
    "kill": "Only a graphic that hasn't been approved can be killed; withdraw an approved one.",
    "withdraw": "Only an approved graphic can be withdrawn.",
}
# Agent runs a redraft may add: on one card (its first draft and a correction's count too), and on
# one replay. They keep one producer from spending the agents' daily runs (AGENT_DAILY_RUNS).
REDRAFT_CARD_RUNS = 5
REDRAFT_REPLAY_RUNS = 30
# Edits a producer may make: on one card, and on one replay. Each edit's wording goes to the
# Translator in both languages (translator.py), so they keep one producer from spending the free
# tier's monthly characters.
EDIT_CARD_VERSIONS = 5
EDIT_REPLAY_VERSIONS = 30


class Refused(Exception):
    """An action the desk won't take, with the HTTP status and what to tell the producer."""

    def __init__(self, status: int, message: str, problems: list[str] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.problems = problems or []


class Push(Protocol):
    async def send(self, run_id: str, message: dict) -> None: ...


@dataclass(frozen=True)
class _Insight:
    topic: str
    status: str
    status_by: str | None
    agent_state: str
    facts: dict
    facts_version: int
    evidence: list[str]
    version: int
    card_evidence: list[str]


async def _authorize(conn: Connection, run_id: str, viewer: str) -> None:
    cur = await conn.execute("select viewer, status from runs where run_id = %s", (run_id,))
    run = await cur.fetchone()
    if run is None:
        raise Refused(404, "There's no such replay.")
    if run["viewer"] is None or run["viewer"] != viewer:
        raise Refused(403, "Only the viewer who started this replay can produce it.")
    if run["status"] != "running":
        raise Refused(409, "The replay has ended.")


async def _insight(conn: Connection, run_id: str, insight_id: str) -> _Insight:
    # The row is locked on its own: a lock that waits on another writer's new version would, with a
    # join to the versions, recheck the join against the old version and find no row.
    cur = await conn.execute(
        "select topic, status, status_by, agent_state, live, facts, facts_version, evidence, version"
        " from insights where run_id = %s and insight_id = %s for update",
        (run_id, insight_id),
    )
    row = await cur.fetchone()
    if row is None:
        raise Refused(404, "There's no such graphic in this replay.")
    if not row["live"]:
        raise Refused(409, "That moment came before the replay's start, so it isn't offered for air.")
    cur = await conn.execute(
        "select card -> 'evidence' as card_evidence from insight_versions"
        " where run_id = %s and insight_id = %s and version = %s",
        (run_id, insight_id, row["version"]),
    )
    version = await cur.fetchone()
    return _Insight(
        row["topic"],
        row["status"],
        row["status_by"],
        row["agent_state"],
        row["facts"],
        row["facts_version"],
        list(row["evidence"]),
        row["version"],
        list((version or {}).get("card_evidence") or []),
    )


class Desk:
    def __init__(self, pool: Pool, push: Push) -> None:
        self.pool = pool
        self.push = push

    async def set_mode(self, run_id: str, viewer: str, mode: Literal["auto", "manual"]) -> str:
        async with self.pool.connection() as conn, conn.transaction():
            await _authorize(conn, run_id, viewer)
            await conn.execute("update runs set producer = %s where run_id = %s", (mode, run_id))
        log.info("run %s: graphics approved %s", run_id, "automatically" if mode == "auto" else "by the producer")
        return mode

    async def act(self, run_id: str, insight_id: str, viewer: str, action: Action, draft: Draft | None = None) -> dict:
        """Take the action and return the push for the changed card, which viewers are sent too."""
        async with self.pool.connection() as conn, conn.transaction():
            await _authorize(conn, run_id, viewer)
            insight = await _insight(conn, run_id, insight_id)
            key = (run_id, insight_id)
            if action in _TO:
                if insight.status not in _FROM[action]:
                    raise Refused(409, _REFUSED[action])
                if action == "approve" and insight.agent_state in ("pending", "drafting"):
                    # The draft on its way would replace the wording being approved.
                    raise Refused(409, "An agent is drafting it; approve it once its draft is in.")
                await conn.execute(
                    "update insights set status = %s, status_by = 'producer', status_at = now(), updated_at = now()"
                    " where run_id = %s and insight_id = %s",
                    (_TO[action], *key),
                )
            elif action == "redraft":
                await self._redraft(conn, key, insight)
            else:
                if draft is None:
                    raise Refused(422, "An edit needs the new wording.")
                await self._edit(conn, key, insight, draft)
            rev = await next_rev(conn, run_id)
            # The desk acts on live insights only (_insight), so there is always one push.
            message = (await push_insights(conn, run_id, {insight_id: rev}))[0]
        log.info("run %s: producer %s %s", run_id, action, insight_id)
        try:
            await asyncio.wait_for(self.push.send(run_id, message), PUSH_SECONDS)
        except Exception:
            # Viewers notice the gap in revisions and fetch the snapshot.
            log.exception("push failed for %s/%s", run_id, insight_id)
        return message

    async def _redraft(self, conn: Connection, key: tuple[str, str], insight: _Insight) -> None:
        if insight.agent_state == "off":
            raise Refused(409, "No agent writes this kind of card; edit it instead.")
        if insight.agent_state in ("pending", "drafting"):
            raise Refused(409, "An agent is drafting it already.")
        if insight.status == "approved" and insight.status_by == "producer":
            raise Refused(409, "It's on air with wording you approved; withdraw it before asking for a redraft.")
        cur = await conn.execute(
            "select count(*) filter (where insight_id = %s) as card, count(*) as replay from agent_runs where run_id = %s",
            (key[1], key[0]),
        )
        used = await cur.fetchone() or {"card": 0, "replay": 0}
        if used["card"] >= REDRAFT_CARD_RUNS:
            raise Refused(409, "This card has had all the agent drafts it gets; edit the wording instead.")
        if used["replay"] >= REDRAFT_REPLAY_RUNS:
            raise Refused(409, "This replay has used all its agent drafts; edit the wording instead.")
        # A fresh job: it joins the queue now with no claims against it, or it would count as having
        # waited since the moment and fall back at once.
        await conn.execute(
            "update insights set redraft = true, agent_state = 'pending', agent_note = null, agent_attempts = 0,"
            " agent_lease = null, queued_at = now(), updated_at = now() where run_id = %s and insight_id = %s",
            key,
        )
        await conn.execute("select pg_notify(%s, %s)", (AGENT_CHANNEL, key[0]))

    async def _edit(self, conn: Connection, key: tuple[str, str], insight: _Insight, draft: Draft) -> None:
        if insight.agent_state in ("pending", "drafting"):
            raise Refused(409, "An agent is drafting it; wait for its draft before editing.")
        cur = await conn.execute(
            "select count(*) filter (where insight_id = %s) as card, count(*) as replay from insight_versions"
            " where run_id = %s and source = 'producer'",
            (key[1], key[0]),
        )
        used = await cur.fetchone() or {"card": 0, "replay": 0}
        if used["card"] >= EDIT_CARD_VERSIONS:
            raise Refused(409, "This card has had all the edits it gets.")
        if used["replay"] >= EDIT_REPLAY_VERSIONS:
            raise Refused(409, "This replay has used all its edits.")
        facts = facts_from_json(insight.facts)
        events = {*insight.evidence, *insight.card_evidence, *(e for f in facts.values() for e in f.events)}
        problems = check(draft, facts, events, limits_for(insight.topic))
        if problems:
            raise Refused(422, "The edit didn't pass the checks.", problems)
        cur = await conn.execute(
            "select coalesce(max(version), 0) + 1 as next from insight_versions where run_id = %s and insight_id = %s",
            key,
        )
        version = int((await cur.fetchone() or {"next": 1})["next"])
        await conn.execute(
            "insert into insight_versions (run_id, insight_id, version, source, facts_version, draft, card, provenance)"
            " values (%s, %s, %s, 'producer', %s, %s, %s, %s)",
            (
                *key,
                version,
                insight.facts_version,
                Jsonb(draft.model_dump()),
                Jsonb(render(draft, facts).to_json()),
                Jsonb({"source": "producer", "edited_from": insight.version, "checks": "passed"}),
            ),
        )
        await conn.execute(
            "update insights set version = %s, updated_at = now() where run_id = %s and insight_id = %s",
            (version, *key),
        )


class ModeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    viewer: str = Field(pattern=VIEWER_PATTERN)
    mode: Literal["auto", "manual"]


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    viewer: str = Field(pattern=VIEWER_PATTERN)
    action: Action
    draft: Draft | None = None


def create_app(desk: Desk) -> FastAPI:
    app = FastAPI(title="Footnote producer's desk")

    def refused(error: Refused) -> JSONResponse:
        return JSONResponse({"error": error.message, "problems": error.problems}, status_code=error.status)

    @app.post("/runs/{run_id}/producer")
    async def set_mode(run_id: str, body: ModeRequest) -> JSONResponse:
        try:
            return JSONResponse({"producer": await desk.set_mode(run_id, body.viewer, body.mode)})
        except Refused as error:
            return refused(error)

    @app.post("/runs/{run_id}/insights/{insight_id}")
    async def act(run_id: str, insight_id: str, body: ActionRequest) -> JSONResponse:
        try:
            return JSONResponse(await desk.act(run_id, insight_id, body.viewer, body.action, body.draft))
        except Refused as error:
            return refused(error)

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok"}

    return app
