"""The SQL, against a real Postgres: migrations, the processor's store with insights and the
tracking, the agents' claims, versions and fallbacks, and the producer's desk. Each test gets a
fresh database.

Needs FOOTNOTE_TEST_DATABASE_URL, a connection string for a role that may create databases (CI runs
a Postgres service; locally any Postgres 17 will do). Skipped without it.
"""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from collections.abc import AsyncIterator

import psycopg
import pytest
from psycopg import AsyncConnection
from psycopg.conninfo import make_conninfo
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from footnote.agents import desk as desk_module
from footnote.agents.desk import (
    EDIT_CARD_VERSIONS,
    EDIT_REPLAY_VERSIONS,
    REDRAFT_CARD_RUNS,
    REDRAFT_REPLAY_RUNS,
    Desk,
    Refused,
)
from footnote.agents.store import AgentStore, PostgresSource
from footnote.agents.translator import TranslationStore, TranslationWorker
from footnote.db.connect import Pool
from footnote.db.migrate import migrate
from footnote.insights.draft import Draft, Sentence
from footnote.insights.facts import Fact
from footnote.insights.translation import names_of, protect, unprotect
from footnote.live import pitch
from footnote.live.analysis import Analysis
from footnote.live.contract import KIND_CONTROL, KIND_FEED, wire
from footnote.live.match import Match, data_dir, load_match
from footnote.live.overlay import OverlayItem
from footnote.live.timeline import Timeline
from footnote.processor.core import Incoming, Processor
from footnote.processor.store import PostgresStore
from footnote.replayer.schedule import plan

DATABASE_URL = os.environ.get("FOOTNOTE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="FOOTNOTE_TEST_DATABASE_URL is not set")

RUN_ID = "fedcba9876543210"
VIEWER = "0f8e2a4c-5b6d-4e7f-8a9b-0c1d2e3f4a5b"


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


def _replay(
    showcase: Match, start_minute: int, *, end: bool, viewer: str | None = None, producer: str = "auto"
) -> list[Incoming]:
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
    start = {"type": "run_start", "run": descriptor, "viewer": viewer, "producer": producer}
    items = [Incoming(RUN_ID, KIND_CONTROL, start, 1, 2)]
    items += [Incoming(RUN_ID, KIND_FEED, m, 3, 4, backfill=True) for m in p.backfill]
    items += [Incoming(RUN_ID, KIND_FEED, m, 5, 6) for step in p.steps for m in step.messages]
    if end:
        items.append(Incoming(RUN_ID, KIND_CONTROL, {"type": "run_end", "run_id": RUN_ID, "reason": "finished"}, 7, 8))
    return items


async def _play(
    pool: Pool,
    showcase: Match,
    analysis: Analysis,
    *,
    end: bool,
    viewer: str | None = None,
    producer: str = "auto",
) -> tuple[PostgresStore, Pushed]:
    store, push = PostgresStore(pool), Pushed()
    await store.put_match(showcase.meta)
    processor = Processor(showcase, store, push, analysis=analysis)
    items = _replay(showcase, 81, end=end, viewer=viewer, producer=producer)
    for i in range(0, len(items), 100):
        await processor.handle(items[i : i + 100])
    return store, push


async def _one(pool: Pool, query: str, *params: object) -> dict:
    async with pool.connection() as conn:
        row = await (await conn.execute(query, params)).fetchone()
    assert row is not None
    return row


async def _agents_fall_back(pool: Pool) -> list[dict]:
    """Every job waiting for an agent ends with the template standing, as a timed-out draft would;
    returns the pushes."""
    agents = AgentStore(pool)
    pushes = [
        await agents.fall_back(c, "No agent draft within 45 s; the template stands.")
        for c in await agents.claim(10, 60)
    ]
    return [p for p in pushes if p is not None]


async def test_migrations_apply_once(pool: Pool) -> None:
    assert await migrate(pool) == []
    row = await _one(pool, "select array_agg(version order by version) as v from schema_migrations")
    assert row["v"] == [
        "0001_runs",
        "0002_insights",
        "0003_queued_at",
        "0004_overlay",
        "0005_insight_pushes",
        "0006_translations",
    ]


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

    # The catch-up for viewers joining at 81': live, approved like any card, pushed with the backfill's
    # end, and the agents' to draft.
    catch_up = await _one(
        pool,
        "select i.live, i.agent_state, i.status, i.placement, i.seq = (r.descriptor ->> 'backfill_seq')::int as at_start"
        " from insights i join runs r using (run_id) where i.run_id = %s and i.insight_id = 'catchup'",
        RUN_ID,
    )
    assert catch_up == {
        "live": True,
        "agent_state": "pending",
        "status": "approved",
        "placement": "side_panel",
        "at_start": True,
    }
    assert pushed[0]["insight"]["insight_id"] == "catchup"

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
    """From 81', three moments want an agent: the catch-up for viewers joining there, the restated
    goal and the full-time recap. The correction notice keeps its template."""
    await _play(pool, showcase, analysis, end=False)
    agents = AgentStore(pool)
    catch_up = await agents.claim(1, 60)
    first = await agents.claim(1, 60)
    second = await agents.claim(10, 60)
    assert [c.insight_id for c in catch_up] == ["catchup"]  # oldest first: queued at the backfill's end
    assert catch_up[0].kind == "recap" and catch_up[0].topic == "catch_up"
    assert [c.insight_id for c in first] == ["goal-e1586"]
    assert [c.insight_id for c in second] == ["ft"]
    assert await agents.claim(10, 60) == []  # all three are being drafted
    goal, recap = first[0], second[0]
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

    fallen = await agents.fall_back(recap, "No agent draft within 30 s; the template stands.")
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

    # The replay ends: whatever is still waiting is dropped, a draft still being written included
    # (the catch-up, and the goal restated meanwhile).
    async with pool.connection() as conn:
        await conn.execute("update runs set status = 'finished' where run_id = %s", (RUN_ID,))
    assert await agents.drop_ended() == 2
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
    # Written again only for a redraft, or when the kept one fails today's checks: the fresh one wins.
    await agents.cache("key-1", "run-2", draft, facts, {"e1586"})
    hit = await agents.cached("key-1")
    assert hit is not None and hit.agent_run_id == "run-2" and hit.facts == facts and hit.events == {"e1586"}
    assert await agents.cached("key-2") is None


async def test_the_match_tools_read_the_stored_feed(pool: Pool, showcase: Match, analysis: Analysis) -> None:
    await _play(pool, showcase, analysis, end=False)
    source = PostgresSource(pool)
    row = await source.insight(RUN_ID, "goal-e1586")
    assert row is not None and row["seq"] == 1620 and row["facts_version"] == 2
    feed = await source.feed(RUN_ID, row["seq"])
    assert [m["seq"] for m in feed] == list(range(1, 1621))
    assert await source.insight(RUN_ID, "no-such-insight") is None


async def test_each_insight_is_an_overlay_item_held_to_the_moment_behind_it(
    pool: Pool, showcase: Match, analysis: Analysis
) -> None:
    """Every pushed insight is an item of the overlay contract; shown_seq names the feed message
    behind its current state, so a delayed viewer holds it until their playback reaches that."""
    _, push = await _play(pool, showcase, analysis, end=True)
    pushed = [m["insight"] for m in push.sent if m["type"] == "insight"]
    assert pushed
    for item in pushed:
        OverlayItem.model_validate(item)
        assert item["match_id"] == showcase.match_id and item["shown_seq"] >= item["seq"]

    feed = {m["seq"]: m for m in showcase.feed}
    goal = await _one(pool, "select to_jsonb(c) as doc from insight_cards c where insight_id = 'goal-e1586'")
    doc = goal["doc"]
    amendment = next(m for m in showcase.feed if m["type"] == "amendment")
    assert doc["shown_seq"] == amendment["seq"]  # restated by the correction
    assert doc["shown_at"] == {
        "period": amendment["period"],
        "t": amendment["t"],
        "minute": amendment["minute"],
        "added_minute": amendment["added_minute"],
    }
    assert doc["ts"] == feed[doc["shown_seq"]]["ts"]
    assert doc["placement"] == "lower_third" and doc["duration"] == 12.0 and doc["motion"] == "animated"
    assert doc["fields"]["moment.scorer"] == "Femi Adeyani"
    assert doc["status"] == "approved" and doc["status_by"] == "auto"

    # History, from the backfill, is never offered for air; segments and stats wait for a stoppage.
    early = await _one(pool, "select status, status_by from insight_cards where insight_id = 'goal-e0391'")
    assert early == {"status": "drafted", "status_by": None}
    held = [i for i in pushed if i["kind"] in ("segment", "stat")]
    assert held and all(i["hold"] == "stoppage" and i["duration"] is None for i in held)

    # Web PubSub bills in 2 KB units. An item with its fields can take two: a run sends a few dozen
    # of them against well over a thousand events, which each fit in one (tests/test_analysis.py).
    assert max(len(wire(m).encode()) for m in push.sent if m["type"] == "insight") <= 3800


async def test_the_live_pushes_are_kept_with_their_rows(pool: Pool, showcase: Match, analysis: Analysis) -> None:
    await _play(pool, showcase, analysis, end=False)
    async with pool.connection() as conn:
        cur = await conn.execute("select seq, push from feed_events where run_id = %s order by seq", (RUN_ID,))
        rows = await cur.fetchall()
    kept = [r for r in rows if r["push"] is not None]
    backfill_seq = kept[0]["seq"]
    assert kept[0]["push"]["type"] == "snapshot" and kept[0]["push"]["seq"] == backfill_seq
    assert all(r["push"] is None for r in rows if r["seq"] < backfill_seq)
    assert [r["seq"] for r in kept] == list(range(backfill_seq, rows[-1]["seq"] + 1))
    assert all(r["push"]["type"] == "event" and "timing" not in r["push"] for r in kept[1:])


async def test_graphics_wait_for_a_producer_who_approves_by_hand(
    pool: Pool, showcase: Match, analysis: Analysis
) -> None:
    await _play(pool, showcase, analysis, end=False, viewer=VIEWER, producer="manual")
    row = await _one(pool, "select viewer, producer from runs where run_id = %s", RUN_ID)
    assert row == {"viewer": VIEWER, "producer": "manual"}
    statuses = await _one(
        pool, "select array_agg(distinct status) as s from insights where run_id = %s and live", RUN_ID
    )
    assert statuses["s"] == ["drafted"]


async def test_a_correction_sends_an_approved_card_back_to_the_producer(
    pool: Pool, showcase: Match, analysis: Analysis
) -> None:
    """Approved by hand before the 84' correction, the 81' goal's card is drafted again once the
    correction restates it: the producer approved what it said before."""
    store, push = PostgresStore(pool), Pushed()
    await store.put_match(showcase.meta)
    processor = Processor(showcase, store, push, analysis=analysis)
    items = _replay(showcase, 81, end=False, viewer=VIEWER, producer="manual")
    amendment = next(i for i, item in enumerate(items) if item.body.get("type") == "amendment")
    await processor.handle(items[:amendment])
    await _agents_fall_back(pool)
    desk = Desk(pool, Pushed())
    await desk.act(RUN_ID, "goal-e1586", VIEWER, "approve")
    await processor.handle(items[amendment:])
    row = await _one(pool, "select status, status_by, facts_version from insights where insight_id = 'goal-e1586'")
    assert row == {"status": "drafted", "status_by": "correction", "facts_version": 2}


@pytest.mark.parametrize(
    ("started", "switched_to", "after"),
    [
        # Approved by hand, then the producer lets the rest through: the corrected card still waits.
        ("manual", "auto", {"status": "drafted", "status_by": "correction"}),
        # Approved automatically, then the producer takes over: nobody approved the old wording by hand.
        ("auto", "manual", {"status": "approved", "status_by": "auto"}),
    ],
)
async def test_who_approved_a_card_decides_what_a_correction_does(
    pool: Pool, showcase: Match, analysis: Analysis, started: str, switched_to: str, after: dict
) -> None:
    store, push = PostgresStore(pool), Pushed()
    await store.put_match(showcase.meta)
    processor = Processor(showcase, store, push, analysis=analysis)
    items = _replay(showcase, 81, end=False, viewer=VIEWER, producer=started)
    amendment = next(i for i, item in enumerate(items) if item.body.get("type") == "amendment")
    await processor.handle(items[:amendment])
    await _agents_fall_back(pool)
    desk = Desk(pool, Pushed())
    if started == "manual":
        await desk.act(RUN_ID, "goal-e1586", VIEWER, "approve")
    await desk.set_mode(RUN_ID, VIEWER, switched_to)
    await processor.handle(items[amendment:])
    row = await _one(pool, "select status, status_by, facts_version from insights where insight_id = 'goal-e1586'")
    assert row == {**after, "facts_version": 2}


async def test_the_desk_acts_only_for_the_viewer_who_started_the_replay(
    pool: Pool, showcase: Match, analysis: Analysis
) -> None:
    await _play(pool, showcase, analysis, end=False, viewer=VIEWER, producer="manual")
    sent = Pushed()
    desk = Desk(pool, sent)
    with pytest.raises(Refused) as refused:
        await desk.act(RUN_ID, "goal-e1586", "11111111-2222-4333-8444-555555555555", "approve")
    assert refused.value.status == 403
    with pytest.raises(Refused) as refused:
        await desk.act("0000000000000000", "goal-e1586", VIEWER, "approve")
    assert refused.value.status == 404
    with pytest.raises(Refused) as refused:
        await desk.act(RUN_ID, "goal-e0391", VIEWER, "approve")  # history, from the backfill
    assert refused.value.status == 409
    with pytest.raises(Refused) as refused:
        await desk.act(RUN_ID, "goal-e1586", VIEWER, "approve")  # its restated job waits for an agent
    assert refused.value.status == 409 and "drafting" in refused.value.message
    await _agents_fall_back(pool)

    rev = (await _one(pool, "select insight_rev from runs where run_id = %s", RUN_ID))["insight_rev"]
    approved = await desk.act(RUN_ID, "goal-e1586", VIEWER, "approve")
    assert approved["rev"] == rev + 1 and approved["insight"]["status"] == "approved"
    assert approved["insight"]["status_by"] == "producer" and sent.sent == [approved]
    with pytest.raises(Refused) as refused:
        await desk.act(RUN_ID, "goal-e1586", VIEWER, "kill")  # approved: withdraw it instead
    assert refused.value.status == 409
    withdrawn = await desk.act(RUN_ID, "goal-e1586", VIEWER, "withdraw")
    assert withdrawn["insight"]["status"] == "withdrawn" and withdrawn["rev"] == rev + 2

    assert await desk.set_mode(RUN_ID, VIEWER, "auto") == "auto"
    assert (await _one(pool, "select producer from runs where run_id = %s", RUN_ID))["producer"] == "auto"

    async with pool.connection() as conn:
        await conn.execute("update runs set status = 'stopped' where run_id = %s", (RUN_ID,))
    with pytest.raises(Refused) as refused:
        await desk.act(RUN_ID, "goal-e1586", VIEWER, "approve")
    assert refused.value.status == 409


class _Hung:
    """A push that never completes, as one did for a minute on a TLS handshake with Web PubSub."""

    async def send(self, run_id: str, message: dict) -> None:
        await asyncio.sleep(3600)


async def test_the_desk_answers_the_producer_without_waiting_on_a_hung_push(
    pool: Pool, showcase: Match, analysis: Analysis, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _play(pool, showcase, analysis, end=False, viewer=VIEWER, producer="manual")
    await _agents_fall_back(pool)
    monkeypatch.setattr(desk_module, "PUSH_SECONDS", 0.1)
    approved = await asyncio.wait_for(Desk(pool, _Hung()).act(RUN_ID, "goal-e1586", VIEWER, "approve"), 5)
    assert approved["insight"]["status"] == "approved"


async def test_a_redraft_queues_a_fresh_job_past_the_cache(pool: Pool, showcase: Match, analysis: Analysis) -> None:
    await _play(pool, showcase, analysis, end=False, viewer=VIEWER, producer="manual")
    desk = Desk(pool, Pushed())
    with pytest.raises(Refused) as refused:
        await desk.act(RUN_ID, "goal-e1586", VIEWER, "redraft")  # its job is still waiting
    assert refused.value.status == 409
    agents = AgentStore(pool)
    claim = next(c for c in await agents.claim(10, 60) if c.insight_id == "goal-e1586")
    await agents.fall_back(claim, "No agent draft within 45 s; the template stands.")
    async with pool.connection() as conn:
        await conn.execute(
            "update insights set queued_at = now() - interval '5 minutes' where insight_id = 'goal-e1586'"
        )
    redrafted = await desk.act(RUN_ID, "goal-e1586", VIEWER, "redraft")
    assert redrafted["insight"]["agent_state"] == "pending" and redrafted["insight"]["agent_note"] is None
    again = next(c for c in await agents.claim(10, 60) if c.insight_id == "goal-e1586")
    assert again.redraft and again.claims == 1 and again.waited < 10


async def test_an_edit_passes_the_same_checks_as_an_agents_draft(
    pool: Pool, showcase: Match, analysis: Analysis
) -> None:
    await _play(pool, showcase, analysis, end=False, viewer=VIEWER, producer="manual")
    agents = AgentStore(pool)
    for claim in await agents.claim(10, 60):
        await agents.fall_back(claim, "No agent draft within 45 s; the template stands.")
    desk = Desk(pool, Pushed())
    typed = Draft(
        headline="{moment.scorer} makes it 2-1",
        casual=[Sentence(text="A late winner for {moment.club}.", events=["e1586"])],
        analyst=[Sentence(text="The shot came at {moment.shot_speed}.", events=["e1585"])],
    )
    with pytest.raises(Refused) as refused:
        await desk.act(RUN_ID, "goal-e1586", VIEWER, "edit", typed)
    assert refused.value.status == 422
    assert any("figure typed as digits" in p for p in refused.value.problems)

    edit = typed.model_copy(update={"headline": "{moment.scorer} strikes late"})
    edited = await desk.act(RUN_ID, "goal-e1586", VIEWER, "edit", edit)
    card = edited["insight"]
    assert card["source"] == "producer" and card["card"]["headline"] == "Femi Adeyani strikes late"
    assert card["provenance"] == {"source": "producer", "edited_from": 2, "checks": "passed"}
    assert card["status"] == "drafted"  # an edit is not an approval
    cached = await _one(pool, "select count(*) as n from agent_cache")
    assert cached["n"] == 0


async def test_a_producer_approves_only_wording_they_have_seen(pool: Pool, showcase: Match, analysis: Analysis) -> None:
    """An agent's draft can't land on a graphic the producer approved: approving waits for a draft
    in flight, and a redraft needs the graphic off air first."""
    await _play(pool, showcase, analysis, end=False, viewer=VIEWER, producer="manual")
    desk, agents = Desk(pool, Pushed()), AgentStore(pool)
    claims = {c.insight_id: c for c in await agents.claim(10, 60)}  # the agents are drafting
    with pytest.raises(Refused) as refused:
        await desk.act(RUN_ID, "goal-e1586", VIEWER, "approve")
    assert refused.value.status == 409 and "drafting" in refused.value.message
    await agents.fall_back(claims["goal-e1586"], "No agent draft within 45 s; the template stands.")
    approved = await desk.act(RUN_ID, "goal-e1586", VIEWER, "approve")
    assert approved["insight"]["status"] == "approved" and approved["insight"]["status_by"] == "producer"

    with pytest.raises(Refused) as refused:
        await desk.act(RUN_ID, "goal-e1586", VIEWER, "redraft")
    assert refused.value.status == 409 and "withdraw" in refused.value.message
    await desk.act(RUN_ID, "goal-e1586", VIEWER, "withdraw")
    redrafted = await desk.act(RUN_ID, "goal-e1586", VIEWER, "redraft")
    assert redrafted["insight"]["agent_state"] == "pending" and redrafted["insight"]["status"] == "withdrawn"
    with pytest.raises(Refused) as refused:
        await desk.act(RUN_ID, "goal-e1586", VIEWER, "approve")  # "Approve again" waits for the redraft too
    assert refused.value.status == 409


async def test_redrafts_are_limited_per_card_and_per_replay(pool: Pool, showcase: Match, analysis: Analysis) -> None:
    await _play(pool, showcase, analysis, end=False, viewer=VIEWER, producer="manual")
    await _agents_fall_back(pool)
    desk = Desk(pool, Pushed())
    other = await _one(
        pool,
        "select insight_id from insights where run_id = %s and live and agent_state <> 'off'"
        " and insight_id <> 'goal-e1586' order by seq limit 1",
        RUN_ID,
    )

    async def agent_runs(insight_id: str, count: int) -> None:
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.executemany(
                "insert into agent_runs (agent_run_id, run_id, insight_id, facts_version, cache_key, model,"
                " prompt_version) values (%s, %s, %s, 1, 'key', 'gpt-5-mini', 'test')",
                [(uuid.uuid4().hex, RUN_ID, insight_id) for _ in range(count)],
            )

    await agent_runs("goal-e1586", REDRAFT_CARD_RUNS)
    with pytest.raises(Refused) as refused:
        await desk.act(RUN_ID, "goal-e1586", VIEWER, "redraft")
    assert refused.value.status == 409 and "all the agent drafts it gets" in refused.value.message
    await agent_runs("elsewhere", REDRAFT_REPLAY_RUNS - REDRAFT_CARD_RUNS)
    with pytest.raises(Refused) as refused:
        await desk.act(RUN_ID, other["insight_id"], VIEWER, "redraft")
    assert refused.value.status == 409 and "This replay has used all its agent drafts" in refused.value.message


async def test_edits_are_limited_per_card_and_per_replay(pool: Pool, showcase: Match, analysis: Analysis) -> None:
    """Each edit's wording goes to the Translator, so a producer gets a limited number of them."""
    await _play(pool, showcase, analysis, end=False, viewer=VIEWER, producer="manual")
    await _agents_fall_back(pool)
    desk = Desk(pool, Pushed())
    edit = Draft(
        headline="{moment.scorer} strikes late",
        casual=[Sentence(text="A late winner for {moment.club}.", events=["e1586"])],
        analyst=[Sentence(text="The shot came at {moment.shot_speed}.", events=["e1585"])],
    )
    async with pool.connection() as conn:
        rows = await (
            await conn.execute(
                "select insight_id from insights where run_id = %s and live and insight_id <> 'goal-e1586'"
                " and agent_state not in ('pending', 'drafting') order by seq limit 2",
                (RUN_ID,),
            )
        ).fetchall()
    filler, target = (row["insight_id"] for row in rows)

    async def producer_versions(insight_id: str, count: int) -> None:
        async with pool.connection() as conn:
            for _ in range(count):
                await conn.execute(
                    "insert into insight_versions (run_id, insight_id, version, source, facts_version, draft, card,"
                    " provenance) select run_id, insight_id, max(version) + 1, 'producer', 1, '{}', '{}', '{}'"
                    " from insight_versions where run_id = %s and insight_id = %s group by run_id, insight_id",
                    (RUN_ID, insight_id),
                )

    await producer_versions("goal-e1586", EDIT_CARD_VERSIONS)
    with pytest.raises(Refused) as refused:
        await desk.act(RUN_ID, "goal-e1586", VIEWER, "edit", edit)
    assert refused.value.status == 409 and "all the edits it gets" in refused.value.message

    await producer_versions(filler, EDIT_REPLAY_VERSIONS - EDIT_CARD_VERSIONS)
    with pytest.raises(Refused) as refused:
        await desk.act(RUN_ID, target, VIEWER, "edit", edit)  # none of its own, but the replay's are spent
    assert refused.value.status == 409 and "This replay has used all its edits" in refused.value.message


async def test_every_insight_push_is_stored_as_it_was_sent(pool: Pool, showcase: Match, analysis: Analysis) -> None:
    """The processor's, the agents' and the desk's pushes are kept, so a page that loads later has
    every state a card went through."""
    _, push = await _play(pool, showcase, analysis, end=False, viewer=VIEWER, producer="manual")
    fallen = await _agents_fall_back(pool)
    approved = await Desk(pool, Pushed()).act(RUN_ID, "goal-e1586", VIEWER, "approve")
    sent = [m for m in push.sent if m["type"] == "insight"] + fallen + [approved]
    async with pool.connection() as conn:
        cur = await conn.execute("select rev, push from insight_pushes where run_id = %s order by rev", (RUN_ID,))
        rows = await cur.fetchall()
    as_sent = sorted(({k: v for k, v in m.items() if k != "timing"} for m in sent), key=lambda m: m["rev"])
    assert [r["push"] for r in rows] == as_sent
    assert all(r["rev"] == r["push"]["rev"] for r in rows)
    assert "goal-e0391" not in {r["push"]["insight"]["insight_id"] for r in rows}  # history: snapshot only


async def test_a_desk_action_that_waits_on_another_writer_still_finds_the_card(
    pool: Pool, showcase: Match, analysis: Analysis
) -> None:
    """The desk locks the card while another writer's new version is uncommitted, as an agent's
    publish or a correction would be, and acts on that version once it lands."""
    await _play(pool, showcase, analysis, end=False, viewer=VIEWER, producer="manual")
    await _agents_fall_back(pool)
    desk = Desk(pool, Pushed())
    async with pool.connection() as conn:
        async with conn.transaction():
            row = await (
                await conn.execute(
                    "select version from insights where run_id = %s and insight_id = 'goal-e1586' for update", (RUN_ID,)
                )
            ).fetchone()
            assert row is not None
            await conn.execute(
                "insert into insight_versions (run_id, insight_id, version, source, facts_version, draft, card, provenance)"
                " select run_id, insight_id, version + 1, source, facts_version, draft, card, provenance"
                " from insight_versions where run_id = %s and insight_id = 'goal-e1586' and version = %s",
                (RUN_ID, row["version"]),
            )
            await conn.execute(
                "update insights set version = version + 1 where run_id = %s and insight_id = 'goal-e1586'", (RUN_ID,)
            )
            acting = asyncio.create_task(desk.act(RUN_ID, "goal-e1586", VIEWER, "approve"))
            await asyncio.sleep(0.5)
            assert not acting.done()  # waiting for the row lock
        approved = await acting
    assert approved["insight"]["status"] == "approved" and approved["insight"]["version"] == row["version"] + 1


class Mirror:
    """A translator that hands each text back marked with its language, names and figures kept; in
    French, if asked, it drops the figures, as a bad translation might."""

    def __init__(self, drop_french_figures: bool = False, fail: bool = False) -> None:
        self.drop = drop_french_figures
        self.fail = fail
        self.calls = 0

    async def translate(self, texts: list[str], languages: tuple[str, ...]) -> list[dict[str, str]]:
        self.calls += 1
        if self.fail:
            raise ConnectionError("Translator unavailable")
        return [
            {lang: (re.sub(r"\d", "", t) if self.drop and lang == "fr" else t) + f" [{lang}]" for lang in languages}
            for t in texts
        ]


async def test_cards_are_translated_checked_and_pushed_again(pool: Pool, showcase: Match, analysis: Analysis) -> None:
    await _play(pool, showcase, analysis, end=False)
    push = Pushed()
    store = TranslationStore(pool)
    worker = TranslationWorker(store, push, Mirror(drop_french_figures=True), names_of(showcase.meta), batch=50)
    before = await _one(pool, "select updated_at from insights where insight_id = 'goal-e1586'")
    # The live cards wait first, then the history a catch-up lists (the replay starts at 81').
    waiting = [
        (await _one(pool, "select live from insights where run_id = %s and insight_id = %s", RUN_ID, p.insight_id))[
            "live"
        ]
        for p in await store.pending(100)
    ]
    assert waiting == sorted(waiting, reverse=True) and True in waiting and False in waiting
    # Each card goes with the half it means by "the half": the 23' goal's the first, the 81' goal's the
    # second, and the catch-up from 81' tells both. The half changes what is sent, so it keys the cache.
    halves = {p.insight_id: p.half for p in await store.pending(100)}
    assert (halves["goal-e0391"], halves["goal-e1586"], halves["catchup"]) == (1, 2, None)
    assert worker.key({"casual": "Late in the half."}, 1) != worker.key({"casual": "Late in the half."}, None)
    assert await worker.drain() > 0
    history = (await _one(pool, "select to_jsonb(c) as doc from insight_cards c where insight_id = 'goal-e0391'"))[
        "doc"
    ]
    assert history["live"] is False and set(history["translations"]) == {"es"}

    # Spanish passed the check and is on the item; French lost its figures, so it is kept with its
    # problems and never shown.
    doc = (
        await _one(pool, "select to_jsonb(c) - 'run_id' as doc from insight_cards c where insight_id = 'goal-e1586'")
    )["doc"]
    OverlayItem.model_validate(doc)
    assert set(doc["translations"]) == {"es"}
    english = unprotect(protect(doc["card"]["casual"], names_of(showcase.meta), half=2))
    assert doc["translations"]["es"]["casual"] == english + " [es]"
    failed = await _one(
        pool, "select problems from card_translations where insight_id = 'goal-e1586' and lang = 'fr' and card is null"
    )
    assert any("figures" in p for p in failed["problems"])
    # The card is pushed again with its translations, as a new state a page keeps.
    pushed = [m for m in push.sent if m["insight"]["insight_id"] == "goal-e1586"]
    assert pushed and pushed[-1]["insight"]["translations"]["es"]
    assert pushed[-1]["insight"]["updated_at"] != before["updated_at"].isoformat()
    revs = [m["rev"] for m in push.sent]
    assert revs == sorted(revs) and len(set(revs)) == len(revs)
    assert max(len(wire(m).encode()) for m in push.sent) <= 4096  # two of Web PubSub's billing units

    # Nothing is left to translate; translated again, the same wording comes from the cache.
    assert await worker.drain() == 0
    async with pool.connection() as conn:
        await conn.execute("delete from card_translations")
    offline = Mirror(fail=True)
    again = TranslationWorker(store, Pushed(), offline, names_of(showcase.meta), batch=50)
    assert await again.drain() > 0 and offline.calls == 0


async def test_a_failing_translator_leaves_the_cards_to_try_again(
    pool: Pool, showcase: Match, analysis: Analysis
) -> None:
    await _play(pool, showcase, analysis, end=False)
    worker = TranslationWorker(TranslationStore(pool), Pushed(), Mirror(fail=True), names_of(showcase.meta))
    with pytest.raises(ConnectionError):
        await worker.drain()
    assert (await _one(pool, "select count(*) as n from card_translations"))["n"] == 0
    assert len(await TranslationStore(pool).pending(50)) > 0


async def test_the_tracking_is_stored_once_per_file(pool: Pool, showcase: Match) -> None:
    store = PostgresStore(pool)
    await store.put_match(showcase.meta)
    cut = pitch.load(data_dir() / "matches" / showcase.match_id / "tracking.npz")
    assert await store.put_tracking(showcase.match_id, cut)
    assert not await store.put_tracking(showcase.match_id, cut)
    row = await _one(
        pool,
        "select m.tracking, (select count(*) from tracking_chunks c where c.match_id = m.match_id) as chunks"
        " from matches m where m.match_id = %s",
        showcase.match_id,
    )
    assert row["chunks"] == len(cut.chunks) and row["tracking"] == cut.layout
    first = await _one(pool, "select frames from tracking_chunks where period = 1 and chunk = 0")
    assert bytes(first["frames"]) == cut.chunks[0][2]
