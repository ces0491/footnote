"""The agents service's Postgres store: jobs, drafts, the cache and the record of every agent run.

A job is an insight whose `agent_state` the processor left at 'pending'. `claim` takes a few at a
time with `for update skip locked`, so two workers never take the same one, and marks them
'drafting' under a lease: if a worker dies mid-draft the lease runs out and the job is claimed
again. Writing a result locks the insight and checks its facts are still the ones the job started
from; a correction that restated the insight in the meantime has already queued a fresh job, so the
stale result is dropped (`superseded`).
"""

from __future__ import annotations

from dataclasses import dataclass

from psycopg.types.json import Jsonb

from footnote.db.connect import Pool
from footnote.db.insights import Connection, cards, insight_push, next_rev
from footnote.insights.draft import Draft, render
from footnote.insights.facts import Facts, facts_from_json, facts_to_json

# Claims a job may take before it falls back for good: a job that keeps killing workers isn't retried.
MAX_CLAIMS = 3


@dataclass(frozen=True)
class Claim:
    run_id: str
    match_id: str
    insight_id: str
    kind: str
    topic: str
    seq: int
    facts: dict
    facts_version: int
    redraft: bool
    claims: int
    waited: float  # seconds since the insight was found


@dataclass(frozen=True)
class Cached:
    agent_run_id: str
    draft: Draft
    facts: Facts
    events: frozenset[str]


_CLAIM = """
with picked as (
    select i.run_id, i.insight_id
      from insights i
      join runs r on r.run_id = i.run_id
     where r.status = 'running'
       and (i.agent_state = 'pending' or (i.agent_state = 'drafting' and i.agent_lease < now()))
     order by i.created_at
     limit %s
       for update of i skip locked
)
update insights i
   set agent_state = 'drafting',
       agent_lease = now() + make_interval(secs => %s),
       agent_attempts = i.agent_attempts + 1,
       updated_at = now()
  from picked, runs r
 where i.run_id = picked.run_id and i.insight_id = picked.insight_id and r.run_id = i.run_id
returning i.run_id, r.match_id, i.insight_id, i.kind, i.topic, i.seq, i.facts, i.facts_version, i.redraft,
          i.agent_attempts as claims, extract(epoch from now() - i.created_at)::float as waited
"""


class AgentStore:
    def __init__(self, pool: Pool) -> None:
        self.pool = pool

    async def claim(self, limit: int, lease_seconds: float) -> list[Claim]:
        async with self.pool.connection() as conn:
            rows = await (await conn.execute(_CLAIM, (limit, lease_seconds))).fetchall()
        return [Claim(**row) for row in rows]

    async def drop_ended(self) -> int:
        """Give up on jobs whose replay has ended: nobody is left to see the draft."""
        async with self.pool.connection() as conn:
            cur = await conn.execute(
                "update insights i set agent_state = 'fallback', agent_lease = null, updated_at = now(),"
                " agent_note = 'The replay ended before an agent drafted it.'"
                " from runs r where r.run_id = i.run_id and r.status <> 'running'"
                " and i.agent_state in ('pending', 'drafting')"
            )
            return cur.rowcount

    async def runs_today(self) -> int:
        async with self.pool.connection() as conn:
            cur = await conn.execute(
                "select count(*) as n from agent_runs where started_at >= date_trunc('day', now(), 'UTC')"
            )
            row = await cur.fetchone()
        return int(row["n"]) if row else 0

    async def cached(self, cache_key: str) -> Cached | None:
        async with self.pool.connection() as conn:
            cur = await conn.execute(
                "select agent_run_id, draft, facts, events from agent_cache where cache_key = %s", (cache_key,)
            )
            row = await cur.fetchone()
        if row is None:
            return None
        return Cached(
            row["agent_run_id"],
            Draft.model_validate(row["draft"]),
            facts_from_json(row["facts"]),
            frozenset(row["events"]),
        )

    async def cache(self, cache_key: str, agent_run_id: str, draft: Draft, facts: Facts, events: set[str]) -> None:
        async with self.pool.connection() as conn:
            await conn.execute(
                "insert into agent_cache (cache_key, agent_run_id, draft, facts, events) values (%s, %s, %s, %s, %s)"
                " on conflict (cache_key) do nothing",
                (
                    cache_key,
                    agent_run_id,
                    Jsonb(draft.model_dump()),
                    Jsonb(facts_to_json(facts)),
                    Jsonb(sorted(events)),
                ),
            )

    async def start_run(self, agent_run_id: str, claim: Claim, cache_key: str, model: str, prompt_version: str) -> None:
        async with self.pool.connection() as conn:
            await conn.execute(
                "insert into agent_runs (agent_run_id, run_id, insight_id, facts_version, cache_key, model, prompt_version)"
                " values (%s, %s, %s, %s, %s, %s, %s)",
                (agent_run_id, claim.run_id, claim.insight_id, claim.facts_version, cache_key, model, prompt_version),
            )

    async def finish_run(self, agent_run_id: str, **fields: object) -> None:
        """Record how an agent run ended: outcome, attempts, tokens, latency, problems, tool calls."""
        columns = ("outcome", "attempts", "input_tokens", "output_tokens", "reasoning_tokens", "latency_ms", "error")
        json_columns = ("problems", "tool_calls", "draft")
        values = [fields.get(c) for c in columns] + [
            None if fields.get(c) is None else Jsonb(fields[c]) for c in json_columns
        ]
        assignments = ", ".join(f"{c} = %s" for c in (*columns, *json_columns))
        async with self.pool.connection() as conn:
            await conn.execute(
                f"update agent_runs set finished_at = now(), {assignments} where agent_run_id = %s",
                (*values, agent_run_id),
            )

    async def publish(self, claim: Claim, draft: Draft, facts: Facts, provenance: dict) -> dict | None:
        """Make the agent's draft the version viewers see; returns its push, or None if superseded."""
        async with self.pool.connection() as conn, conn.transaction():
            if not await _still_current(conn, claim):
                return None
            cur = await conn.execute(
                "select coalesce(max(version), 0) + 1 as next from insight_versions where run_id = %s and insight_id = %s",
                (claim.run_id, claim.insight_id),
            )
            version = int((await cur.fetchone() or {"next": 1})["next"])
            await conn.execute(
                "insert into insight_versions (run_id, insight_id, version, source, facts_version, draft, card, provenance)"
                " values (%s, %s, %s, 'agent', %s, %s, %s, %s)",
                (
                    claim.run_id,
                    claim.insight_id,
                    version,
                    claim.facts_version,
                    Jsonb(draft.model_dump()),
                    Jsonb(render(draft, facts).to_json()),
                    Jsonb(provenance),
                ),
            )
            await conn.execute(
                "update insights set version = %s, agent_state = 'done', agent_note = null, agent_lease = null,"
                " redraft = false, updated_at = now() where run_id = %s and insight_id = %s",
                (version, claim.run_id, claim.insight_id),
            )
            return await _push(conn, claim)

    async def fall_back(self, claim: Claim, note: str) -> dict | None:
        """Leave the template on screen and say why; returns the push, or None if superseded."""
        async with self.pool.connection() as conn, conn.transaction():
            if not await _still_current(conn, claim):
                return None
            await conn.execute(
                "update insights set agent_state = 'fallback', agent_note = %s, agent_lease = null, redraft = false,"
                " updated_at = now() where run_id = %s and insight_id = %s",
                (note, claim.run_id, claim.insight_id),
            )
            return await _push(conn, claim)


async def _still_current(conn: Connection, claim: Claim) -> bool:
    cur = await conn.execute(
        "select facts_version from insights where run_id = %s and insight_id = %s for update",
        (claim.run_id, claim.insight_id),
    )
    row = await cur.fetchone()
    return row is not None and int(row["facts_version"]) == claim.facts_version


async def _push(conn: Connection, claim: Claim) -> dict | None:
    rev = await next_rev(conn, claim.run_id)
    docs = await cards(conn, claim.run_id, [claim.insight_id])
    return insight_push(claim.run_id, rev, docs[0]) if docs and docs[0]["live"] else None


class PostgresSource:
    """The match tools' view of the store (footnote.tools.scope.Source)."""

    def __init__(self, pool: Pool) -> None:
        self.pool = pool

    async def insight(self, run_id: str, insight_id: str) -> dict | None:
        async with self.pool.connection() as conn:
            cur = await conn.execute(
                "select insight_id, kind, topic, seq, at, rank, reason, evidence, corrects, flag, facts, facts_version,"
                " template from insights where run_id = %s and insight_id = %s",
                (run_id, insight_id),
            )
            return await cur.fetchone()

    async def feed(self, run_id: str, upto_seq: int) -> list[dict]:
        async with self.pool.connection() as conn:
            cur = await conn.execute(
                "select body from feed_events where run_id = %s and seq <= %s order by seq", (run_id, upto_seq)
            )
            return [row["body"] for row in await cur.fetchall()]
