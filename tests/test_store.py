"""The SQL, against a real Postgres: migrations, the processor's store with insights, and the agents'
claims, versions and fallbacks. Each test gets a fresh database.

Needs FOOTNOTE_TEST_DATABASE_URL, a connection string for a role that may create databases (CI runs
a Postgres service; locally any Postgres 17 will do). Skipped without it.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import psycopg
import pytest
from psycopg import AsyncConnection
from psycopg.conninfo import make_conninfo
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from footnote.agents.store import AgentStore, PostgresSource
from footnote.db.connect import Pool
from footnote.db.migrate import migrate
from footnote.insights.draft import Draft, Sentence
from footnote.insights.facts import Fact
from footnote.live.analysis import Analysis
from footnote.live.contract import KIND_CONTROL, KIND_FEED
from footnote.live.match import Match, load_match
from footnote.live.timeline import Timeline
from footnote.processor.core import Incoming, Processor
from footnote.processor.store import PostgresStore
from footnote.replayer.schedule import plan

DATABASE_URL = os.environ.get("FOOTNOTE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="FOOTNOTE_TEST_DATABASE_URL is not set")

RUN_ID = "fedcba9876543210"


class Pushed:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, run_id: str, message: dict) -> None:
        self.sent.append(message)


@pytest.fixture
async def pool() -> AsyncIterator[Pool]:
    assert DATABASE_URL is not None
    name = f"footnote_test_{uuid.uuid4().hex[:12]}"
    async with await psycopg.AsyncConnection.connect(DATABASE_URL, autocommit=True) as admin:
        await admin.execute(f'create database "{name}"')
    test_pool: Pool = AsyncConnectionPool(
        make_conninfo(DATABASE_URL, dbname=name),
        connection_class=AsyncConnection[DictRow],
        kwargs={"row_factory": dict_row},
        min_size=1,
        max_size=4,
        open=False,
    )
    await test_pool.open(wait=True)
    try:
        await migrate(test_pool)
        yield test_pool
    finally:
        await test_pool.close()
        async with await psycopg.AsyncConnection.connect(DATABASE_URL, autocommit=True) as admin:
            await admin.execute(f'drop database "{name}" with (force)')


@pytest.fixture(scope="module")
def showcase() -> Match:
    return load_match()


@pytest.fixture(scope="module")
def analysis(showcase: Match) -> Analysis:
    return Analysis.load(showcase)


def _replay(showcase: Match, start_minute: int, *, end: bool) -> list[Incoming]:
    timeline = Timeline.from_feed(showcase.feed)
    start = timeline.jump_point(start_minute)
    p = plan(showcase.feed, timeline, start, 4.0)
    descriptor = {
        "run_id": RUN_ID,
        "match_id": showcase.match_id,
        "speed": 4.0,
        "start_minute": start_minute,
        "start_replay": start,
        "started_at": 1_800_000_000_000,
        "backfill_seq": p.backfill_seq,
        "timeline": timeline.describe(),
    }
    items = [Incoming(RUN_ID, KIND_CONTROL, {"type": "run_start", "run": descriptor}, 1, 2)]
    items += [Incoming(RUN_ID, KIND_FEED, m, 3, 4, backfill=True) for m in p.backfill]
    items += [Incoming(RUN_ID, KIND_FEED, m, 5, 6) for step in p.steps for m in step.messages]
    if end:
        items.append(Incoming(RUN_ID, KIND_CONTROL, {"type": "run_end", "run_id": RUN_ID, "reason": "finished"}, 7, 8))
    return items


async def _play(pool: Pool, showcase: Match, analysis: Analysis, *, end: bool) -> tuple[PostgresStore, Pushed]:
    store, push = PostgresStore(pool), Pushed()
    await store.put_match(showcase.meta)
    processor = Processor(showcase, store, push, analysis=analysis)
    items = _replay(showcase, 81, end=end)
    for i in range(0, len(items), 100):
        await processor.handle(items[i : i + 100])
    return store, push


async def _one(pool: Pool, query: str, *params: object) -> dict:
    async with pool.connection() as conn:
        row = await (await conn.execute(query, params)).fetchone()
    assert row is not None
    return row


async def test_migrations_apply_once(pool: Pool) -> None:
    assert await migrate(pool) == []
    row = await _one(pool, "select array_agg(version order by version) as v from schema_migrations")
    assert row["v"] == ["0001_runs", "0002_insights", "0003_queued_at"]


async def test_the_processor_stores_insights_with_their_feed(pool: Pool, showcase: Match, analysis: Analysis) -> None:
    _, push = await _play(pool, showcase, analysis, end=True)
    pushed = [m for m in push.sent if m["type"] == "insight"]
    revs = [m["rev"] for m in pushed]
    assert revs == sorted(revs) and len(set(revs)) == len(revs)
    run = await _one(pool, "select insight_rev from runs where run_id = %s", RUN_ID)
    assert run["insight_rev"] >= max(revs)

    # Found in the backfill: stored as history, never pushed.
    early = await _one(
        pool, "select live, agent_state from insights where run_id = %s and insight_id = 'goal-e0391'", RUN_ID
    )
    assert early == {"live": False, "agent_state": "off"}
    assert "goal-e0391" not in {m["insight"]["insight_id"] for m in pushed}

    # The 81st-minute goal: the template's version, then the restated one after the correction.
    goal = await _one(
        pool,
        "select version, facts_version, topic, flag, agent_state from insights where run_id = %s and insight_id = 'goal-e1586'",
        RUN_ID,
    )
    assert goal["version"] == 2 and goal["facts_version"] == 2 and goal["topic"] == "goal"
    assert goal["flag"]["event_id"] == "e1586" and goal["agent_state"] == "pending"
    card = await _one(
        pool, "select source, card from insight_cards where run_id = %s and insight_id = 'goal-e1586'", RUN_ID
    )
    assert card["source"] == "template" and card["card"]["headline"] == "Femi Adeyani scores"
    first = await _one(
        pool,
        "select card from insight_versions where run_id = %s and insight_id = 'goal-e1586' and version = 1",
        RUN_ID,
    )
    assert first["card"]["headline"] == "Own goal: Jory Penhallow"

    # What a viewer is sent is the view's row, without the working fields.
    last = pushed[-1]["insight"]
    assert {"insight_id", "kind", "rank", "reason", "evidence", "card", "source", "provenance", "agent_state"} <= set(
        last
    )
    assert "facts" not in last and "template" not in last


async def test_agents_claim_publish_and_fall_back(pool: Pool, showcase: Match, analysis: Analysis) -> None:
    """From 81', two moments want an agent: the restated goal and the correction notice."""
    await _play(pool, showcase, analysis, end=False)
    agents = AgentStore(pool)
    first = await agents.claim(1, 60)
    second = await agents.claim(10, 60)
    assert [c.insight_id for c in first] == ["goal-e1586"]  # oldest first
    assert [c.insight_id for c in second] == ["correction-e1586-v2"]
    assert await agents.claim(10, 60) == []  # both are being drafted
    goal, correction = first[0], second[0]
    assert goal.claims == 1 and goal.match_id == showcase.match_id
    assert goal.facts_version == 2 and goal.facts["moment.scorer"]["display"] == "Femi Adeyani"

    draft = Draft(
        headline="{moment.scorer} puts Kingsferry ahead",
        casual=[Sentence(text="{moment.score_line} late on.", events=["e1586"])],
        analyst=[Sentence(text="The shot came at {moment.shot_speed}.", events=["e1585"])],
    )
    facts = {
        key: Fact(v["value"], v["display"], v["about"], tuple(v.get("events", ()))) for key, v in goal.facts.items()
    }
    rev_before = (await _one(pool, "select insight_rev from runs where run_id = %s", RUN_ID))["insight_rev"]
    push = await agents.publish(goal, draft, facts, {"source": "agent", "agent_run_id": "a1"})
    assert push is not None and push["rev"] == rev_before + 1
    assert push["insight"]["source"] == "agent" and push["insight"]["version"] == 3
    assert push["insight"]["card"]["headline"] == "Femi Adeyani puts Kingsferry ahead"
    assert push["insight"]["agent_state"] == "done"

    fallen = await agents.fall_back(correction, "No agent draft within 30 s; the template stands.")
    assert fallen is not None and fallen["insight"]["agent_state"] == "fallback" and fallen["rev"] == rev_before + 2
    assert fallen["insight"]["agent_note"].startswith("No agent draft") and fallen["insight"]["source"] == "template"

    # A restatement while a draft was being written makes the draft stale: nothing is written.
    async with pool.connection() as conn:
        await conn.execute(
            "update insights set facts_version = facts_version + 1, agent_state = 'pending'"
            " where run_id = %s and insight_id = 'goal-e1586'",
            (RUN_ID,),
        )
    assert await agents.publish(goal, draft, facts, {"source": "agent"}) is None
    assert await agents.fall_back(goal, "x") is None

    # The replay ends: whatever is still waiting is dropped.
    async with pool.connection() as conn:
        await conn.execute("update runs set status = 'finished' where run_id = %s", (RUN_ID,))
    assert await agents.drop_ended() == 1
    assert await agents.claim(10, 60) == []


async def test_a_restated_insight_is_a_fresh_job(pool: Pool, showcase: Match, analysis: Analysis) -> None:
    """At 1x the 84' correction comes over three minutes after the 81' goal. The restated goal's job
    must wait from the restatement, with no claims against it, or it falls back without a draft."""
    store, push = PostgresStore(pool), Pushed()
    await store.put_match(showcase.meta)
    processor = Processor(showcase, store, push, analysis=analysis)
    items = _replay(showcase, 81, end=False)
    amendment = next(i for i, item in enumerate(items) if item.body.get("type") == "amendment")
    for i in range(0, amendment, 100):
        await processor.handle(items[i : min(i + 100, amendment)])
    agents = AgentStore(pool)
    first = [c for c in await agents.claim(10, 60) if c.insight_id == "goal-e1586"]
    assert first and first[0].claims == 1 and first[0].facts_version == 1
    async with pool.connection() as conn:  # as if the goal had been found three minutes ago
        await conn.execute(
            "update insights set created_at = now() - interval '190 seconds', queued_at = now() - interval '190 seconds'"
            " where run_id = %s and insight_id = 'goal-e1586'",
            (RUN_ID,),
        )
    await processor.handle(items[amendment:])
    again = [c for c in await agents.claim(10, 60) if c.insight_id == "goal-e1586"]
    assert again and again[0].facts_version == 2
    assert again[0].claims == 1 and again[0].waited < 10
    row = await _one(
        pool,
        "select queued_at > created_at as fresh from insights where run_id = %s and insight_id = 'goal-e1586'",
        RUN_ID,
    )
    assert row["fresh"]


async def test_a_lapsed_lease_is_claimed_again(pool: Pool, showcase: Match, analysis: Analysis) -> None:
    await _play(pool, showcase, analysis, end=False)
    agents = AgentStore(pool)
    claimed = await agents.claim(1, 0.01)
    async with pool.connection() as conn:
        await conn.execute("select pg_sleep(0.05)")
    again = await agents.claim(1, 60)
    assert [c.insight_id for c in again] == [claimed[0].insight_id] and again[0].claims == 2


async def test_the_run_log_cache_and_daily_count(pool: Pool, showcase: Match, analysis: Analysis) -> None:
    await _play(pool, showcase, analysis, end=False)
    agents = AgentStore(pool)
    claim = (await agents.claim(1, 60))[0]
    assert await agents.runs_today() == 0
    await agents.start_run("run-1", claim, "key-1", "gpt-5-mini", "p1")
    await agents.finish_run(
        "run-1", outcome="accepted", attempts=1, input_tokens=900, tool_calls=[{"name": "get_moment"}]
    )
    assert await agents.runs_today() == 1
    logged = await _one(
        pool, "select outcome, input_tokens, tool_calls, finished_at from agent_runs where agent_run_id = 'run-1'"
    )
    assert logged["outcome"] == "accepted" and logged["input_tokens"] == 900 and logged["finished_at"] is not None

    draft = Draft(headline="h", casual=[Sentence(text="c", events=[])], analyst=[Sentence(text="a", events=[])])
    facts = {"moment.minute": Fact(81, "81'", "minute", ("e1586",))}
    await agents.cache("key-1", "run-1", draft, facts, {"e1586"})
    await agents.cache("key-1", "run-2", draft, facts, {"e1586"})  # first one wins
    hit = await agents.cached("key-1")
    assert hit is not None and hit.agent_run_id == "run-1" and hit.facts == facts and hit.events == {"e1586"}
    assert await agents.cached("key-2") is None


async def test_the_match_tools_read_the_stored_feed(pool: Pool, showcase: Match, analysis: Analysis) -> None:
    await _play(pool, showcase, analysis, end=False)
    source = PostgresSource(pool)
    row = await source.insight(RUN_ID, "goal-e1586")
    assert row is not None and row["seq"] == 1620 and row["facts_version"] == 2
    feed = await source.feed(RUN_ID, row["seq"])
    assert [m["seq"] for m in feed] == list(range(1, 1621))
    assert await source.insight(RUN_ID, "no-such-insight") is None
