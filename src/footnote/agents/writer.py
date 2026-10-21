"""Drafting one card: a writer agent and the code that checks it, as an Agent Framework workflow.

    Job -> writer --Attempt--> checker --(passes)----------> Outcome (accepted)
             ^                    |
             +------Revise--------+   (fails, with a try left)
                                  +--(fails, none left)----> Outcome (rejected)

The writer is an Agent Framework `Agent` on a chat client (Foundry in the service, a scripted client
in the tests). Its only tools are the match tools, reached over MCP with the job's scope in headers
the model never sees (footnote.tools.scope). A function middleware keeps a log of every call: the
facts and events each returned are all the checker lets the draft use (footnote.insights.draft). A
revision runs in the same session, so the writer sees its draft and the tool results again.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from agent_framework import (
    Agent,
    Executor,
    FunctionInvocationContext,
    FunctionMiddleware,
    MCPStreamableHTTPTool,
    SupportsChatGetResponse,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)
from pydantic import ValidationError

from footnote.agents.prompts import first_prompt, instructions, revision_prompt, writer_name
from footnote.insights.draft import Draft, check, limits_for, render, same_words
from footnote.insights.facts import Facts, facts_from_json
from footnote.tools.scope import INSIGHT_HEADER, RUN_HEADER

MAX_ATTEMPTS = 2

# Part of the agents' cache key (worker.py): change it when the drafting around the model changes in
# a way that could change a draft or the facts it is checked against. 2026-10-20.2: tool logs no
# longer mix between concurrent jobs (ToolLog). 2026-10-21.1: limits by topic (recaps), and a draft
# that repeats the template's casual line is sent back. 2026-10-21.2: a recap keeps the template's
# heading.
WRITER_VERSION = "2026-10-21.2"

# A recap's heading is its graphic's fixed one ("Half-time: Saltmarsh 0–1 Kingsferry", "What you
# missed, up to 59'"), so the template's stands whatever the writer puts there: one headed the
# full-time recap "Insight ft.", from the job it was given.
RECAP_TOPICS = frozenset({"half_time", "full_time", "catch_up"})


@dataclass(frozen=True)
class Job:
    run_id: str
    insight_id: str
    kind: str
    topic: str
    facts_version: int


# Compared by identity: Agent Framework reuses a client's cached function-middleware pipeline when
# a run's middleware compares equal to the last one's, and two empty logs compare equal by value, so
# concurrent jobs on one client would otherwise share the first job's log.
@dataclass(eq=False)
class ToolLog(FunctionMiddleware):
    """Every match-tool call in one job, the facts and events the calls returned, and the template's
    wording of the moment, from get_moment."""

    calls: list[dict] = field(default_factory=list)
    facts: Facts = field(default_factory=dict)
    events: set[str] = field(default_factory=set)
    template: Draft | None = None

    async def process(self, context: FunctionInvocationContext, call_next: Any) -> None:
        await call_next()
        arguments = context.arguments if isinstance(context.arguments, dict) else dict(context.arguments)
        self.calls.append({"name": context.function.name, "arguments": arguments})
        for text in _texts(context.result):
            try:
                body = json.loads(text)
            except ValueError:
                continue
            if isinstance(body, dict):
                self.facts |= facts_from_json(body.get("facts", {}))
                self.events |= set(body.get("events", []))
                if context.function.name == "get_moment" and isinstance(body.get("template"), dict):
                    self.template = Draft.model_validate(body["template"])

    @property
    def read_the_moment(self) -> bool:
        return any(call["name"] == "get_moment" for call in self.calls)


def _texts(result: Any) -> list[str]:
    if isinstance(result, str):
        return [result]
    if isinstance(result, list):
        return [str(getattr(c, "text", "")) for c in result if getattr(c, "text", None)]
    return []


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0

    def add(self, details: Any) -> None:
        if details is None:
            return
        get = details.get if isinstance(details, dict) else lambda k: getattr(details, k, None)
        self.input_tokens += int(get("input_token_count") or 0)
        self.output_tokens += int(get("output_token_count") or 0)
        self.reasoning_tokens += int(get("reasoning_output_token_count") or 0)


@dataclass(frozen=True)
class Attempt:
    job: Job
    number: int
    draft: Draft | None
    problems: list[str]  # why the reply couldn't be read as a draft, if it couldn't


@dataclass(frozen=True)
class Revise:
    job: Job
    number: int
    problems: list[str]


@dataclass(frozen=True)
class Outcome:
    accepted: bool
    draft: Draft | None
    problems: list[str]
    attempts: int


class Writer(Executor):
    def __init__(self, agent: Agent, tools: MCPStreamableHTTPTool, log: ToolLog, options: dict, usage: Usage) -> None:
        super().__init__(id="writer")
        self.agent = agent
        self.tools = tools
        self.log = log
        self.options = options
        self.usage = usage
        self.session = agent.create_session()

    @handler
    async def write(self, job: Job, ctx: WorkflowContext[Attempt]) -> None:
        await ctx.send_message(await self._attempt(job, 1, first_prompt(job.insight_id)))

    @handler
    async def revise(self, revise: Revise, ctx: WorkflowContext[Attempt]) -> None:
        await ctx.send_message(await self._attempt(revise.job, revise.number, revision_prompt(revise.problems)))

    async def _attempt(self, job: Job, number: int, prompt: str) -> Attempt:
        response = await self.agent.run(
            prompt,
            session=self.session,
            tools=[self.tools],
            middleware=[self.log],
            options={**self.options, "response_format": Draft},
            function_invocation_kwargs={"run_id": job.run_id, "insight_id": job.insight_id},
        )
        self.usage.add(response.usage_details)
        try:
            draft = response.value
        except (ValidationError, ValueError) as exc:
            return Attempt(job, number, None, [f"the reply wasn't a draft in the format asked for: {exc}"])
        if not isinstance(draft, Draft):
            return Attempt(job, number, None, ["the reply wasn't a draft in the format asked for"])
        return Attempt(job, number, draft, [])


class Checker(Executor):
    def __init__(self, log: ToolLog, max_attempts: int) -> None:
        super().__init__(id="checker")
        self.log = log
        self.max_attempts = max_attempts

    @handler
    async def check(self, attempt: Attempt, ctx: WorkflowContext[Revise, Outcome]) -> None:
        problems = list(attempt.problems)
        draft = attempt.draft
        if draft is not None and attempt.job.topic in RECAP_TOPICS and self.log.template is not None:
            draft = draft.model_copy(update={"headline": self.log.template.headline})
        if draft is not None:
            if not self.log.read_the_moment:
                problems.append("call get_moment first: the card has to be about the moment it was asked for")
            problems += check(draft, self.log.facts, self.log.events, limits_for(attempt.job.topic))
            if not problems and self._repeats_the_template(draft):
                problems.append(
                    "casual: it repeats the template's line, which stands anyway; say in your own words what"
                    " the moment means for the match, from the reason it was picked"
                )
        if not problems:
            await ctx.yield_output(Outcome(True, draft, [], attempt.number))
        elif attempt.number < self.max_attempts:
            await ctx.send_message(Revise(attempt.job, attempt.number + 1, problems))
        else:
            await ctx.yield_output(Outcome(False, draft, problems, attempt.number))

    def _repeats_the_template(self, draft: Draft) -> bool:
        """Whether the casual line is the template's, word for word: an agent's card that adds
        nothing is no reason to replace the template's."""
        template = self.log.template
        if template is None:
            return False
        try:
            theirs = render(template, self.log.facts).casual
        except KeyError:
            return False
        return same_words(render(draft, self.log.facts).casual, theirs)


@dataclass
class Drafted:
    """What drafting one job came to, with what it cost and what the writer read."""

    outcome: Outcome
    log: ToolLog
    usage: Usage
    latency_ms: int


def scope_headers(kwargs: dict[str, Any]) -> dict[str, str]:
    """The job's scope for the match tools, from the run's invocation arguments, never the model's."""
    return {RUN_HEADER: str(kwargs["run_id"]), INSIGHT_HEADER: str(kwargs["insight_id"])}


async def draft(
    job: Job, client: SupportsChatGetResponse, mcp_url: str, options: dict, max_attempts: int = MAX_ATTEMPTS
) -> Drafted:
    """Run the workflow for one job against the match tools at `mcp_url`."""
    started = time.perf_counter()
    log, usage = ToolLog(), Usage()
    tools = MCPStreamableHTTPTool(
        "match",
        mcp_url,
        header_provider=scope_headers,
        load_prompts=False,
        request_timeout=20,
    )
    agent = Agent(client, instructions(job.kind), name=writer_name(job.kind))
    async with tools:
        writer = Writer(agent, tools, log, options, usage)
        checker = Checker(log, max_attempts)
        workflow = WorkflowBuilder(start_executor=writer).add_edge(writer, checker).add_edge(checker, writer).build()
        result = await workflow.run(job)
    outputs = [o for o in result.get_outputs() if isinstance(o, Outcome)]
    outcome = outputs[-1] if outputs else Outcome(False, None, ["the workflow ended without a result"], 0)
    return Drafted(outcome, log, usage, round((time.perf_counter() - started) * 1000))
