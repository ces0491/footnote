"""The processor's Postgres store: runs, their feed, their state view and their insights, and the
tracking the pitch view draws."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime

from psycopg.types.json import Jsonb

from footnote.db.connect import Pool
from footnote.db.insights import AGENT_CHANNEL, Connection, next_rev, push_insights
from footnote.insights.book import Change, Insight
from footnote.live.contract import ProducerMode
from footnote.live.pitch import PitchTracking
from footnote.processor.core import FeedRow

log = logging.getLogger(__name__)

_ATTEMPTS = 3
SLOW_SAVE_SECONDS = 1.0  # a write slower than this is logged


def _ts(ms: int | None) -> datetime | None:
    return None if ms is None else datetime.fromtimestamp(ms / 1000, tz=UTC)


class PostgresStore:
    def __init__(self, pool: Pool) -> None:
        self.pool = pool

    async def put_match(self, meta: dict) -> None:
        await self._retry(
            "insert into matches (match_id, meta) values (%s, %s)"
            " on conflict (match_id) do update set meta = excluded.meta, updated_at = now()",
            (meta["match_id"], Jsonb(meta)),
        )

    async def put_tracking(self, match_id: str, tracking: PitchTracking) -> bool:
        """Store the match's tracking for the pitch view, unless this file is stored already;
        returns whether it wrote anything."""
        async with self.pool.connection() as conn, conn.transaction():
            cur = await conn.execute(
                "select tracking ->> 'digest' as digest from matches where match_id = %s for update", (match_id,)
            )
            row = await cur.fetchone()
            if row is not None and row["digest"] == tracking.layout["digest"]:
                return False
            await conn.execute("delete from tracking_chunks where match_id = %s", (match_id,))
            async with conn.cursor() as copier:
                async with copier.copy("copy tracking_chunks (match_id, period, chunk, frames) from stdin") as copy:
                    for period, chunk, frames in tracking.chunks:
                        await copy.write_row((match_id, period, chunk, frames))
            await conn.execute(
                "update matches set tracking = %s where match_id = %s", (Jsonb(tracking.layout), match_id)
            )
        return True

    async def start_run(self, descriptor: dict, viewer: str | None = None, producer: ProducerMode = "auto") -> bool:
        inserted = await self._retry(
            "insert into runs (run_id, match_id, descriptor, viewer, producer) values (%s, %s, %s, %s, %s)"
            " on conflict (run_id) do nothing",
            (descriptor["run_id"], descriptor["match_id"], Jsonb(descriptor), viewer, producer),
        )
        return inserted == 1

    async def end_run(self, run_id: str, reason: str) -> None:
        await self._retry(
            "update runs set status = %s, ended_at = now() where run_id = %s and status = 'running'", (reason, run_id)
        )

    async def load_run(self, run_id: str) -> tuple[dict, list[dict]] | None:
        async with self.pool.connection() as conn:
            run = await (await conn.execute("select descriptor from runs where run_id = %s", (run_id,))).fetchone()
            if run is None:
                return None
            cur = await conn.execute("select body from feed_events where run_id = %s order by seq", (run_id,))
            return run["descriptor"], [row["body"] for row in await cur.fetchall()]

    async def running_runs(self) -> list[tuple[dict, int]]:
        async with self.pool.connection() as conn:
            cur = await conn.execute(
                "select r.descriptor, coalesce(s.seq, 0) as seq from runs r"
                " left join run_state s on s.run_id = r.run_id where r.status = 'running'"
            )
            return [(row["descriptor"], row["seq"]) for row in await cur.fetchall()]

    async def save(self, rows: list[FeedRow], run_id: str, view: dict | None, changes: list[Change]) -> list[dict]:
        params = [
            (
                r.run_id,
                r.message["seq"],
                r.message["event_id"],
                r.message["version"],
                r.message["type"],
                r.message["period"],
                r.message["clock"],
                Jsonb(r.message),
                _ts(r.published_at),
                _ts(r.enqueued_at),
                None if r.push is None else Jsonb(r.push),
            )
            for r in rows
        ]
        started = time.perf_counter()
        for attempt in range(1, _ATTEMPTS + 1):
            try:
                async with self.pool.connection() as conn, conn.transaction():
                    async with conn.cursor() as cur:
                        await cur.executemany(
                            "insert into feed_events (run_id, seq, event_id, version, type, period, clock, body,"
                            " published_at, enqueued_at, push) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                            " on conflict (run_id, seq) do nothing",
                            params,
                        )
                    if view is not None:
                        await conn.execute(
                            "insert into run_state (run_id, seq, view) values (%s, %s, %s)"
                            " on conflict (run_id) do update set seq = excluded.seq, view = excluded.view,"
                            " updated_at = now()",
                            (run_id, view["seq"], Jsonb(view)),
                        )
                    pushes = await write_insights(conn, run_id, changes) if changes else []
                elapsed = time.perf_counter() - started
                if elapsed > SLOW_SAVE_SECONDS:
                    log.info(
                        "store write for run %s took %.1f s: %d feed rows, %d insight changes",
                        run_id,
                        elapsed,
                        len(rows),
                        len(changes),
                    )
                return pushes
            except Exception:
                if attempt == _ATTEMPTS:
                    raise
                log.warning("store write for run %s failed (attempt %d); retrying", run_id, attempt, exc_info=True)
                await asyncio.sleep(0.2 * 2**attempt)
        raise AssertionError("unreachable")

    async def _retry(self, query: str, params: tuple) -> int:
        """Run one statement, retrying transient failures; returns the rows it affected."""
        for attempt in range(1, _ATTEMPTS + 1):
            try:
                async with self.pool.connection() as conn:
                    cursor = await conn.execute(query, params)
                    return cursor.rowcount
            except Exception:
                if attempt == _ATTEMPTS:
                    raise
                log.warning("store write failed (attempt %d); retrying", attempt, exc_info=True)
                await asyncio.sleep(0.2 * 2**attempt)
        raise AssertionError("unreachable")


# What one batch did to each insight, strongest first: an insert carries all the insight now is, and
# a flag carries the shelf life as well.
_PRECEDENCE = {"new": 0, "restated": 1, "flagged": 2, "ended": 3}

# Inserts and versions skip what is already stored: a batch the store took before a restart. A run
# whose graphics are approved automatically has each live insight approved as it is found; history
# (moments its backfill passed) is never offered for air.
_INSERT_INSIGHT = """
insert into insights (run_id, insight_id, seq, kind, topic, at, until_at, rank, reason, evidence, placement,
                      hold, duration, motion, corrects, live, flag, facts, facts_version, template, agent_state,
                      status, status_by, status_at)
select %(run_id)s, %(insight_id)s, %(seq)s, %(kind)s, %(topic)s, %(at)s, %(until)s, %(rank)s, %(reason)s,
       %(evidence)s, %(placement)s, %(hold)s, %(duration)s, %(motion)s, %(corrects)s, %(live)s, %(flag)s,
       %(facts)s, %(facts_version)s, %(template)s, %(agent_state)s,
       case when run.auto then 'approved' else 'drafted' end,
       case when run.auto then 'auto' end,
       case when run.auto then now() end
  -- One row whatever happens: an insight for a run not on record fails on its foreign key.
  from (select %(live)s and (select producer from runs where run_id = %(run_id)s) is not distinct from 'auto' as auto) run
on conflict (run_id, insight_id) do nothing
"""

_INSERT_VERSION = (
    "insert into insight_versions (run_id, insight_id, version, source, facts_version, draft, card, provenance)"
    " values (%s, %s, %s, 'template', %s, %s, %s, %s) on conflict do nothing"
)


def _template_version(run_id: str, insight: Insight, version: int) -> tuple:
    return (
        run_id,
        insight.insight_id,
        version,
        insight.facts_version,
        Jsonb(insight.template.model_dump()),
        Jsonb(insight.card().to_json()),
        Jsonb({"source": "template", "template": insight.topic}),
    )


def _insert_params(run_id: str, insight: Insight) -> dict:
    record = insight.record()
    return {
        **record,
        "run_id": run_id,
        **{k: Jsonb(record[k]) for k in ("at", "until", "evidence", "facts", "template")},
        "flag": None if insight.flag is None else Jsonb(insight.flag),
        "agent_state": "pending" if insight.agent else "off",
    }


async def _restate(conn: Connection, run_id: str, insight: Insight) -> None:
    # The agents add versions too, so the next number comes from the store, under the row lock.
    key = (run_id, insight.insight_id)
    await conn.execute("select 1 from insights where run_id = %s and insight_id = %s for update", key)
    cur = await conn.execute(
        "select coalesce(max(version), 0) + 1 as next from insight_versions where run_id = %s and insight_id = %s", key
    )
    version = int((await cur.fetchone() or {"next": 1})["next"])
    await conn.execute(_INSERT_VERSION, _template_version(run_id, insight, version))
    record = insight.record()
    # A fresh job for the agents: it joins the queue now, with no claims against it yet. A producer
    # who approved the card approved what it said before, so the corrected card waits for them again.
    # Who approved it decides, not the run's mode now: the producer may have switched since.
    await conn.execute(
        "update insights i set topic = %s, seq = %s, evidence = %s, flag = %s, facts = %s, facts_version = %s,"
        " template = %s, version = %s, agent_state = %s, agent_note = null, agent_attempts = 0,"
        " agent_lease = null, queued_at = now(), updated_at = now(),"
        " status = case when was.hand then 'drafted' else i.status end,"
        " status_by = case when was.hand then 'correction' else i.status_by end,"
        " status_at = case when was.hand then now() else i.status_at end"
        " from (select i2.status = 'approved' and i2.status_by = 'producer' as hand from insights i2"
        " where i2.run_id = %s and i2.insight_id = %s) was"
        " where i.run_id = %s and i.insight_id = %s",
        (
            insight.topic,
            insight.seq,
            Jsonb(insight.evidence),
            Jsonb(insight.flag),
            Jsonb(record["facts"]),
            insight.facts_version,
            Jsonb(record["template"]),
            version,
            "pending" if insight.agent else "off",
            *key,
            *key,
        ),
    )


async def write_insights(conn: Connection, run_id: str, changes: list[Change]) -> list[dict]:
    """Store what the batch did to the run's insights; returns the pushes for the live ones.

    New insights and flags go in as pipelined batches, and the run's revisions are taken in one
    statement, so a backfill that finds dozens of insights costs a handful of round trips.
    """
    latest: dict[str, Change] = {}
    for change in changes:
        prior = latest.get(change.insight.insight_id)
        if prior is None or _PRECEDENCE[change.what] < _PRECEDENCE[prior.what]:
            latest[change.insight.insight_id] = change
    if not latest:
        return []
    by_kind: dict[str, list[Insight]] = {"new": [], "restated": [], "flagged": [], "ended": []}
    for change in latest.values():
        by_kind[change.what].append(change.insight)
    async with conn.cursor() as cur:
        if by_kind["new"]:
            await cur.executemany(_INSERT_INSIGHT, [_insert_params(run_id, i) for i in by_kind["new"]])
            await cur.executemany(_INSERT_VERSION, [_template_version(run_id, i, 1) for i in by_kind["new"]])
        if by_kind["flagged"]:
            await cur.executemany(
                "update insights set flag = %s, until_at = %s, updated_at = now() where run_id = %s and insight_id = %s",
                [(Jsonb(i.flag), Jsonb(i.until), run_id, i.insight_id) for i in by_kind["flagged"]],
            )
        if by_kind["ended"]:
            await cur.executemany(
                "update insights set until_at = %s, updated_at = now() where run_id = %s and insight_id = %s",
                [(Jsonb(i.until), run_id, i.insight_id) for i in by_kind["ended"]],
            )
    for insight in by_kind["restated"]:
        await _restate(conn, run_id, insight)
    # One revision per changed insight, in the order the batch changed them.
    last = await next_rev(conn, run_id, len(latest))
    revs = {insight_id: last - len(latest) + 1 + n for n, insight_id in enumerate(latest)}
    if any(c.insight.agent and c.what in ("new", "restated") for c in latest.values()):
        await conn.execute("select pg_notify(%s, %s)", (AGENT_CHANNEL, run_id))
    return await push_insights(conn, run_id, revs)
