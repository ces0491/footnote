"""Drafting the showcase's cases with the agents' own writer, and evaluating what comes back.

Live, the writer runs on the Foundry model as it does in the agents service, against the real match
tools served on localhost, and each case's result can be recorded: the tool calls the writer made,
its last draft, its attempts, latency and tokens. Replayed, a scripted model makes the recorded calls
and gives the recorded draft, so today's checks and evaluators run on the model's real output at no
cost. CI replays (tests/test_evals.py).
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import uvicorn
from agent_framework import (
    BaseChatClient,
    ChatMiddlewareLayer,
    ChatResponse,
    Content,
    FunctionInvocationLayer,
    Message,
    SupportsChatGetResponse,
)
from agent_framework.observability import ChatTelemetryLayer

from footnote.agents.versions import VERSIONS
from footnote.agents.worker import Settings
from footnote.agents.writer import Job, draft
from footnote.evals.cases import Case, CaseSource
from footnote.evals.groundedness import verdict as groundedness_verdict
from footnote.evals.judges import Verdict, evaluate
from footnote.insights.draft import Card, Draft, render
from footnote.insights.facts import Facts
from footnote.live.analysis import Analysis
from footnote.live.match import Match
from footnote.tools.scope import Scopes
from footnote.tools.server import build_server

# The bar a recorded run must clear, in CI and in `python -m footnote.evals replay`: three cards in
# four pass every evaluation.
PASSING_SHARE = 0.75


@dataclass
class Result:
    case: Case
    outcome: str  # accepted, rejected, timeout or error, as the agents service records it
    draft: Draft | None = None
    calls: list[dict] = field(default_factory=list)
    attempts: int = 0
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    problems: list[str] = field(default_factory=list)
    verdicts: list[Verdict] = field(default_factory=list)
    card: Card | None = None
    facts: Facts = field(default_factory=dict)  # what the writer's tools returned
    groundedness: dict | None = None  # the model-judged verdict, from a live run (groundedness.py)

    @property
    def passed(self) -> bool:
        return self.outcome == "accepted" and all(v.passed for v in self.verdicts)

    def recorded(self) -> dict:
        """What a live run keeps of the case for replaying: the model's output, what it cost and how
        the judge found it."""
        return {
            "outcome": self.outcome,
            "calls": self.calls,
            "draft": self.draft.model_dump() if self.draft else None,
            "attempts": self.attempts,
            "latency_ms": self.latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "groundedness": self.groundedness,
        }


@asynccontextmanager
async def match_tools(match: Match, analysis: Analysis, cases: list[Case]) -> AsyncIterator[str]:
    """The match tools for the cases on a free localhost port; yields their MCP URL."""
    app = build_server(Scopes(CaseSource(match, cases), match, analysis, keep=4)).streamable_http_app()
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


async def draft_case(
    case: Case, client: SupportsChatGetResponse, mcp_url: str, options: dict, deadline_seconds: float
) -> Result:
    """One case through the writer workflow, judged as the agents service would and then evaluated."""
    job = Job(case.key, case.insight_id, case.kind, case.topic, case.facts_version)
    started = time.perf_counter()
    try:
        drafted = await asyncio.wait_for(draft(job, client, mcp_url, options), timeout=deadline_seconds)
    except TimeoutError:
        return Result(case, "timeout", latency_ms=round((time.perf_counter() - started) * 1000))
    except Exception as exc:
        return Result(case, "error", problems=[f"{type(exc).__name__}: {exc}"[:500]])
    outcome = drafted.outcome
    result = Result(
        case,
        "accepted" if outcome.accepted else "rejected",
        draft=outcome.draft,
        calls=drafted.log.calls,
        attempts=outcome.attempts,
        latency_ms=drafted.latency_ms,
        input_tokens=drafted.usage.input_tokens,
        output_tokens=drafted.usage.output_tokens,
        problems=outcome.problems,
    )
    if outcome.accepted and outcome.draft is not None:
        result.card = render(outcome.draft, drafted.log.facts)
        result.facts = drafted.log.facts
        result.verdicts = evaluate(case.row, outcome.draft, drafted.log.facts)
    return result


async def judge_groundedness(results: list[Result], judge: Any, concurrency: int = 4) -> None:
    """Add the model-judged groundedness verdict to every accepted card."""
    slots = asyncio.Semaphore(concurrency)

    async def one(result: Result) -> None:
        if result.card is None:
            return
        async with slots:
            try:
                result.groundedness = await judge.judge(result.card, result.facts, str(result.case.row["reason"]))
            except Exception as exc:
                result.groundedness = {"score": None, "passed": False, "reason": f"the judge failed: {exc}"[:300]}
        found = groundedness_verdict(result.groundedness)
        if found is not None:
            result.verdicts.append(found)

    await asyncio.gather(*(one(r) for r in results))


async def run(
    match: Match,
    analysis: Analysis,
    cases: list[Case],
    client_for: Any,
    options: dict,
    *,
    concurrency: int = 3,
    deadline_seconds: float = 45.0,
) -> list[Result]:
    """Every case, `concurrency` at a time, with the chat client `client_for(case)` gives."""
    slots = asyncio.Semaphore(concurrency)
    async with match_tools(match, analysis, cases) as url:

        async def one(case: Case) -> Result:
            async with slots:
                return await draft_case(case, client_for(case), url, options, deadline_seconds)

        return list(await asyncio.gather(*(one(c) for c in cases)))


class Replayed(FunctionInvocationLayer, ChatMiddlewareLayer, ChatTelemetryLayer, BaseChatClient):
    """One case's recorded model: it makes the recorded tool calls, then gives the recorded draft,
    and gives the same draft again if the checks send it back."""

    def __init__(self, recorded: dict) -> None:
        super().__init__()
        self.recorded = recorded

    async def _inner_get_response(self, *, messages: Any, stream: bool, options: Any, **kwargs: Any) -> ChatResponse:
        if str(messages[-1].text).startswith("Write the card"):
            calls = [
                Content.from_function_call(call_id=f"c{n}", name=c["name"], arguments=json.dumps(c["arguments"]))
                for n, c in enumerate(self.recorded["calls"], start=1)
            ]
            return ChatResponse(messages=[Message("assistant", calls)])
        return ChatResponse(messages=[Message("assistant", [json.dumps(self.recorded["draft"])])])


async def replay(match: Match, analysis: Analysis, cases: list[Case], recording: dict) -> list[Result]:
    """Every recorded case through today's writer workflow, checks and evaluators, with the model's
    recorded output. A case that wasn't recorded, or whose model gave no draft, comes back as it was."""
    recorded = recording["cases"]
    playable = [c for c in cases if recorded.get(c.key, {}).get("draft") is not None]
    results = await run(
        match, analysis, playable, lambda c: Replayed(recorded[c.key]), {}, concurrency=4, deadline_seconds=120
    )
    by_key = {r.case.key: r for r in results}
    out = []
    for case in cases:
        if case.key in by_key:
            live = recorded[case.key]
            result = by_key[case.key]
            # The cost, the attempts and the judge's verdict are the live run's; what the replay adds
            # is today's checks and code evaluators.
            result.attempts, result.latency_ms = live["attempts"], live["latency_ms"]
            result.input_tokens, result.output_tokens = live["input_tokens"], live["output_tokens"]
            result.groundedness = live.get("groundedness")
            found = groundedness_verdict(result.groundedness) if result.card is not None else None
            if found is not None:
                result.verdicts.append(found)
            out.append(result)
        else:
            out.append(Result(case, recorded.get(case.key, {}).get("outcome", "not recorded")))
    return out


def stale(recording: dict) -> list[str]:
    """What changed since the recording was made: the parts of the agents' cache key it predates,
    each version with its fingerprint (agents/versions.py), and the writers' reasoning effort."""
    versions = recording.get("versions", {})
    changed = [f"{k} {versions.get(k)} -> {v}" for k, v in VERSIONS.items() if versions.get(k) != v]
    if recording.get("reasoning_effort") != Settings.reasoning_effort:
        changed.append(f"reasoning effort {recording.get('reasoning_effort')} -> {Settings.reasoning_effort}")
    return changed


def passing(results: list[Result]) -> float:
    """The share of cases accepted with every evaluation passed."""
    return sum(r.passed for r in results) / len(results) if results else 0.0
