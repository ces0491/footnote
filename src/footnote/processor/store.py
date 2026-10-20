"""The processor's Postgres store: runs, their feed and their state view."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from psycopg.types.json import Jsonb

from footnote.db.connect import Pool
from footnote.processor.core import FeedRow

log = logging.getLogger(__name__)

_ATTEMPTS = 3


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

    async def start_run(self, descriptor: dict) -> bool:
        inserted = await self._retry(
            "insert into runs (run_id, match_id, descriptor) values (%s, %s, %s) on conflict (run_id) do nothing",
            (descriptor["run_id"], descriptor["match_id"], Jsonb(descriptor)),
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

    async def save(self, rows: list[FeedRow], run_id: str, view: dict | None) -> None:
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
            )
            for r in rows
        ]
        for attempt in range(1, _ATTEMPTS + 1):
            try:
                async with self.pool.connection() as conn, conn.transaction():
                    async with conn.cursor() as cur:
                        await cur.executemany(
                            "insert into feed_events (run_id, seq, event_id, version, type, period, clock, body,"
                            " published_at, enqueued_at) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
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
                return
            except Exception:
                if attempt == _ATTEMPTS:
                    raise
                log.warning("store write for run %s failed (attempt %d); retrying", run_id, attempt, exc_info=True)
                await asyncio.sleep(0.2 * 2**attempt)

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
