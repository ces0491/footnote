"""The agents: the writer workflow and the worker around it, with a scripted model in place of
Foundry and the real match tools served over MCP on localhost."""

from __future__ import annotations

import asyncio
import dataclasses
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
import uvicorn
from agent_framework import (
    BaseChatClient,
    ChatMiddlewareLayer,
    ChatResponse,
    Content,
    FunctionInvocationLayer,
    MCPStreamableHTTPTool,
    Message,
)
from agent_framework.exceptions import ToolExecutionException
from agent_framework.observability import ChatTelemetryLayer

from footnote.agents.store import Cached, Claim
from footnote.agents.worker import Settings, Worker, cache_key
from footnote.agents.writer import Job, draft
from footnote.insights.draft import Draft, render
from footnote.insights.facts import Facts
from footnote.live.analysis import Analysis
from footnote.live.match import Match, load_match
from footnote.live.state import RunState
from footnote.tools.scope import Scopes
from footnote.tools.server import build_server

RUN = "r1"
GOAL = "goal-e0391"


@pytest.fixture(scope="module")
def showcase() -> Match:
    return load_match()


@pytest.fixture(scope="module")
def analysis(showcase: Match) -> Analysis:
    return Analysis.load(showcase)


@pytest.fixture(scope="module")
def rows(showcase: Match, analysis: Analysis) -> dict[str, dict]:
    state = RunState.rebuild(showcase.match_id, showcase.home_id, showcase.away_id, showcase.feed, analysis)
    assert state.book is not None
    return {i.insight_id: i.record() for i in state.book.insights.values()}


class Source:
    def __init__(self, rows: dict[str, dict], feed: list[dict]) -> None:
        self.rows, self.messages = rows, feed

    async def insight(self, run_id: str, insight_id: str) -> dict | None:
        return self.rows.get(insight_id) if run_id == RUN else None

    async def feed(self, run_id: str, upto_seq: int) -> list[dict]:
        return [m for m in self.messages if m["seq"] <= upto_seq]


@asynccontextmanager
async def match_tools(showcase: Match, analysis: Analysis, rows: dict[str, dict]) -> AsyncIterator[str]:
    """The match tools on a free localhost port, for the length of a test."""
    app = build_server(Scopes(Source(rows, showcase.feed), showcase, analysis)).streamable_http_app()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        server.should_exit = True
        await task


GOOD = {
    "headline": "{moment.scorer} breaks the deadlock",
    "casual": [
        {"text": "{moment.club} score against the run of play.", "events": ["e0391"]},
        {
            "text": "{moment.other_club} had been on top for {moment.other_on_top} of the {moment.window} before.",
            "events": [],
        },
    ],
    "analyst": [{"text": "{teams.SAL.name} have had {teams.SAL.possession} of the ball.", "events": []}],
}
TYPED_FIGURE = {**GOOD, "headline": "Goal at 23 minutes"}
# Mid-sentence: a capitalised word at the start of a sentence can't be told from an ordinary one.
INVENTED_NAME = {**GOOD, "headline": "Kingsferry stun Riverton"}


class Scripted(FunctionInvocationLayer, ChatMiddlewareLayer, ChatTelemetryLayer, BaseChatClient):
    """A model that reads the moment and the stats for each new job, then gives the drafts it was
    handed, in order."""

    def __init__(self, *drafts: dict, delay: float = 0.0, fail: bool = False) -> None:
        super().__init__()
        self.drafts = list(drafts)
        self.delay = delay
        self.fail = fail
        self.calls = 0
        self.prompts: list[str] = []

    async def _inner_get_response(self, *, messages: Any, stream: bool, options: Any, **kwargs: Any) -> ChatResponse:
        self.calls += 1
        self.prompts.append(str(messages[-1].text))
        if self.fail:
            raise ConnectionError("model unavailable")
        await asyncio.sleep(self.delay)
        if self.prompts[-1].startswith("Write the card"):
            calls = [
                Content.from_function_call(call_id="c1", name="get_moment", arguments="{}"),
                Content.from_function_call(call_id="c2", name="get_match_stats", arguments="{}"),
            ]
            return ChatResponse(messages=[Message("assistant", calls)], response_id="r1")
        body = self.drafts.pop(0)
        return ChatResponse(
            messages=[Message("assistant", [json.dumps(body)])],
            response_id=f"r{self.calls}",
            usage_details={"input_token_count": 1000, "output_token_count": 200},
        )


async def test_a_draft_that_fails_a_check_is_revised(
    showcase: Match, analysis: Analysis, rows: dict[str, dict]
) -> None:
    client = Scripted(TYPED_FIGURE, GOOD)
    async with match_tools(showcase, analysis, rows) as url:
        drafted = await draft(Job(RUN, GOAL, "moment", 1), client, url, {})
    assert drafted.outcome.accepted and drafted.outcome.attempts == 2
    assert "typed as digits" in client.prompts[-1]  # the revision prompt names the problem
    assert [c["name"] for c in drafted.log.calls] == ["get_moment", "get_match_stats"]
    assert drafted.usage.input_tokens == 2000
    assert drafted.outcome.draft is not None
    card = render(drafted.outcome.draft, drafted.log.facts)
    assert card.headline == "Femi Adeyani breaks the deadlock"
    assert "Saltmarsh had been on top for 66% of the 10 minutes before" in card.casual


async def test_a_draft_that_fails_twice_is_rejected(showcase: Match, analysis: Analysis, rows: dict[str, dict]) -> None:
    async with match_tools(showcase, analysis, rows) as url:
        drafted = await draft(Job(RUN, GOAL, "moment", 1), Scripted(TYPED_FIGURE, INVENTED_NAME), url, {})
    assert not drafted.outcome.accepted and drafted.outcome.attempts == 2
    assert any("'Riverton' isn't a name" in p for p in drafted.outcome.problems)


class Store:
    """The worker's store, in memory."""

    def __init__(self, claims: list[Claim], runs_today: int = 0) -> None:
        self.queue = list(claims)
        self.today = runs_today
        self.runs: dict[str, dict] = {}
        self.entries: dict[str, Cached] = {}
        self.published: list[tuple[Claim, dict]] = []
        self.fallbacks: list[tuple[Claim, str]] = []

    async def claim(self, limit: int, lease_seconds: float) -> list[Claim]:
        taken, self.queue = self.queue[:limit], self.queue[limit:]
        return taken

    async def drop_ended(self) -> int:
        return 0

    async def runs_today(self) -> int:
        return self.today + len(self.runs)

    async def cached(self, key: str) -> Cached | None:
        return self.entries.get(key)

    async def cache(self, key: str, agent_run_id: str, draft: Draft, facts: Facts, events: set[str]) -> None:
        self.entries.setdefault(key, Cached(agent_run_id, draft, facts, frozenset(events)))

    async def start_run(self, agent_run_id: str, claim: Claim, key: str, model: str, prompt_version: str) -> None:
        self.runs[agent_run_id] = {"insight_id": claim.insight_id, "key": key}

    async def finish_run(self, agent_run_id: str, **fields: object) -> None:
        self.runs[agent_run_id] |= fields

    async def publish(self, claim: Claim, draft: Draft, facts: Facts, provenance: dict) -> dict | None:
        card = render(draft, facts).to_json()
        self.published.append((claim, provenance))
        return {
            "type": "insight",
            "run_id": claim.run_id,
            "rev": 1,
            "insight": {"card": card, "provenance": provenance},
        }

    async def fall_back(self, claim: Claim, note: str) -> dict | None:
        self.fallbacks.append((claim, note))
        return {"type": "insight", "run_id": claim.run_id, "rev": 1, "insight": {"agent_note": note}}


class Push:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, run_id: str, message: dict) -> None:
        self.sent.append(message)


def _claim(rows: dict[str, dict], showcase: Match, *, redraft: bool = False, waited: float = 1.0) -> Claim:
    row = rows[GOAL]
    return Claim(
        RUN, showcase.match_id, GOAL, row["kind"], row["topic"], row["seq"], row["facts"], 1, redraft, 1, waited
    )


async def _work(store: Store, client: Scripted, url: str, **settings: Any) -> Push:
    push = Push()
    worker = Worker(store, push, client, url, Settings(model="gpt-5-mini", **settings))
    while await worker.drain():
        await worker.wait_idle()
    return push


async def test_an_accepted_draft_is_published_and_reused(
    showcase: Match, analysis: Analysis, rows: dict[str, dict]
) -> None:
    claim = _claim(rows, showcase)
    store = Store([claim, claim])
    async with match_tools(showcase, analysis, rows) as url:
        client = Scripted(GOOD)
        push = await _work(store, client, url, concurrency=1)
    first, second = (p for _, p in store.published)
    assert first["cached"] is False and first["attempts"] == 1 and first["tools"] == ["get_match_stats", "get_moment"]
    assert second["cached"] is True and second["agent_run_id"] == first["agent_run_id"]
    assert client.calls == 2  # one job's worth: the second came from the cache
    run = store.runs[first["agent_run_id"]]
    assert run["outcome"] == "accepted" and run["input_tokens"] == 1000 and run["key"] == cache_key(claim, "gpt-5-mini")
    assert [m["insight"]["card"]["headline"] for m in push.sent] == ["Femi Adeyani breaks the deadlock"] * 2


async def test_a_redraft_skips_the_cache(showcase: Match, analysis: Analysis, rows: dict[str, dict]) -> None:
    store = Store([_claim(rows, showcase), _claim(rows, showcase, redraft=True)])
    async with match_tools(showcase, analysis, rows) as url:
        client = Scripted(GOOD, GOOD)
        await _work(store, client, url, concurrency=1)
    assert [p["cached"] for _, p in store.published] == [False, False] and client.calls == 4


@pytest.mark.parametrize(
    ("client", "settings", "note"),
    [
        (Scripted(GOOD, delay=1.0), {"deadline_seconds": 0.5}, "No agent draft within 0 s"),
        (Scripted(fail=True), {}, "The agent failed on this one"),
        (Scripted(TYPED_FIGURE, TYPED_FIGURE), {}, "failed the checks"),
    ],
    ids=["slow", "failing", "rejected"],
)
async def test_the_template_stands_when_the_agent_doesnt_deliver(
    showcase: Match, analysis: Analysis, rows: dict[str, dict], client: Scripted, settings: dict, note: str
) -> None:
    store = Store([_claim(rows, showcase)])
    async with match_tools(showcase, analysis, rows) as url:
        push = await _work(store, client, url, **settings)
    assert store.published == [] and len(store.fallbacks) == 1
    assert note in store.fallbacks[0][1] and push.sent[0]["insight"]["agent_note"] == store.fallbacks[0][1]
    (run,) = store.runs.values()
    assert run["outcome"] in ("timeout", "error", "rejected")


async def test_a_restated_insight_cancels_the_draft_for_its_old_facts(
    showcase: Match, analysis: Analysis, rows: dict[str, dict]
) -> None:
    old = _claim(rows, showcase)
    new = dataclasses.replace(old, facts_version=2)
    store = Store([old])
    async with match_tools(showcase, analysis, rows) as url:
        worker = Worker(store, Push(), Scripted(GOOD, GOOD, delay=0.3), url, Settings(model="gpt-5-mini"))
        await worker.drain()  # drafting from the old facts
        await asyncio.sleep(0.1)
        store.queue.append(new)  # a correction restated the insight
        await worker.drain()
        await worker.wait_idle()
    assert sorted(run.get("outcome") for run in store.runs.values()) == ["accepted", "superseded"]
    assert [claim.facts_version for claim, _ in store.published] == [2]


async def test_no_model_call_past_the_limits(showcase: Match, analysis: Analysis, rows: dict[str, dict]) -> None:
    client = Scripted(GOOD)
    spent = Store([_claim(rows, showcase)], runs_today=300)
    stale = Store([_claim(rows, showcase, waited=600)])
    async with match_tools(showcase, analysis, rows) as url:
        await _work(spent, client, url, daily_runs=300)
        await _work(stale, client, url)
    assert client.calls == 0 and spent.runs == {} and stale.runs == {}
    assert "budget is spent" in spent.fallbacks[0][1] and "waited too long" in stale.fallbacks[0][1]


async def test_the_tools_answer_only_for_a_scoped_run(
    showcase: Match, analysis: Analysis, rows: dict[str, dict]
) -> None:
    async with match_tools(showcase, analysis, rows) as url:
        async with MCPStreamableHTTPTool("match", url, load_prompts=False) as tools:
            with pytest.raises(ToolExecutionException, match="only for a scoped agent run"):
                await tools.call_tool("get_moment")
