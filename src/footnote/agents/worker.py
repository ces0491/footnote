"""The agents service's loop: claim jobs, draft them, and publish or fall back.

For each job, in order:

1. The cache. Every replay is the same match, so the same moment gives the same job. A job's key is
   the match, the insight and its facts, the model, and the prompt, tools and writer versions
   (`cache_key`). An accepted draft is reused when the key matches, checked again against the facts
   its writer was shown, unless the producer asked for a fresh draft.
2. The limits. A job that waited too long for a worker, or that would take today's agent runs past
   `daily_runs`, falls back without calling the model.
3. The workflow (writer.py), under `deadline_seconds`, long enough for one revision. An accepted
   draft becomes the version viewers see. A rejected one, a timeout or an error leaves the template's
   version and records why in the insight's `agent_note`, which viewers and the producer see
   (docs/audience.md, P2 and P3).

A correction can restate an insight while its draft is being written; the insight is then pending
again with new facts. Claiming it again cancels the draft still running for the old facts.

Every model call is recorded in `agent_runs`: outcome, attempts, tokens, latency, the problems a
rejected draft had and the tool calls the writer made.
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Protocol

from agent_framework import SupportsChatGetResponse

from footnote.agents.prompts import PROMPT_VERSION
from footnote.agents.store import MAX_CLAIMS, Cached, Claim
from footnote.agents.writer import WRITER_VERSION, Drafted, Job, draft
from footnote.insights.draft import Draft, check
from footnote.insights.facts import Facts
from footnote.tools.server import TOOLS_VERSION

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    model: str  # the Foundry deployment the writers run on
    deadline_seconds: float = 45.0  # from a job's claim to its draft, or the template stays
    queue_seconds: float = 90.0  # how long a job may wait for a worker before it's no use
    daily_runs: int = 150  # agent runs a day (UTC) before every job falls back
    concurrency: int = 3
    reasoning_effort: str = "low"
    max_output_tokens: int = 4000

    @property
    def options(self) -> dict:
        return {"reasoning": {"effort": self.reasoning_effort}, "max_tokens": self.max_output_tokens}


class Store(Protocol):
    async def claim(self, limit: int, lease_seconds: float) -> list[Claim]: ...
    async def drop_ended(self) -> int: ...
    async def runs_today(self) -> int: ...
    async def cached(self, cache_key: str) -> Cached | None: ...
    async def cache(self, cache_key: str, agent_run_id: str, draft: Draft, facts: Facts, events: set[str]) -> None: ...
    async def start_run(
        self, agent_run_id: str, claim: Claim, cache_key: str, model: str, prompt_version: str
    ) -> None: ...
    async def finish_run(self, agent_run_id: str, **fields: object) -> None: ...
    async def publish(self, claim: Claim, draft: Draft, facts: Facts, provenance: dict) -> dict | None: ...
    async def fall_back(self, claim: Claim, note: str) -> dict | None: ...


class Push(Protocol):
    async def send(self, run_id: str, message: dict) -> None: ...


def cache_key(claim: Claim, model: str) -> str:
    """What makes two jobs the same: the moment and its facts, and what drafts it."""
    payload = {
        "match": claim.match_id,
        "insight": claim.insight_id,
        "topic": claim.topic,
        "seq": claim.seq,
        "facts": claim.facts,
        "model": model,
        "prompt": PROMPT_VERSION,
        "tools": TOOLS_VERSION,
        "writer": WRITER_VERSION,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Worker:
    def __init__(
        self, store: Store, push: Push, client: SupportsChatGetResponse, mcp_url: str, settings: Settings
    ) -> None:
        self.store = store
        self.push = push
        self.client = client
        self.mcp_url = mcp_url
        self.settings = settings
        self._slots = asyncio.Semaphore(settings.concurrency)
        self._running: set[asyncio.Task] = set()
        self._drafting: dict[tuple[str, str], asyncio.Task] = {}  # by run and insight

    async def run(self, wake: asyncio.Event, poll_seconds: float = 5.0) -> None:
        """Claim and draft jobs until cancelled, looking again when woken and every `poll_seconds`."""
        while True:
            try:
                await self.drain()
            except Exception:
                log.exception("claiming jobs failed")
            try:
                await asyncio.wait_for(wake.wait(), timeout=poll_seconds)
            except TimeoutError:
                pass
            wake.clear()

    async def drain(self) -> int:
        """Start as many claimed jobs as there are free slots; returns how many started."""
        await self.store.drop_ended()
        free = self.settings.concurrency - len(self._running)
        if free <= 0:
            return 0
        lease = self.settings.deadline_seconds + 30
        claims = await self.store.claim(free, lease)
        for claim in claims:
            key = (claim.run_id, claim.insight_id)
            stale = self._drafting.get(key)
            if stale is not None and not stale.done():
                stale.cancel()  # restated since: its facts are no longer the insight's
            task = asyncio.create_task(self._guarded(claim), name=f"draft {claim.insight_id}")
            self._drafting[key] = task
            self._running.add(task)
            task.add_done_callback(self._running.discard)
            task.add_done_callback(functools.partial(self._forget, key))
        return len(claims)

    def _forget(self, key: tuple[str, str], done: asyncio.Task) -> None:
        if self._drafting.get(key) is done:
            del self._drafting[key]

    async def wait_idle(self) -> None:
        while self._running:
            await asyncio.gather(*list(self._running), return_exceptions=True)

    async def _guarded(self, claim: Claim) -> None:
        async with self._slots:
            try:
                await self.process(claim)
            except Exception:
                log.exception("job %s/%s failed outside the agent", claim.run_id, claim.insight_id)

    async def process(self, claim: Claim) -> None:
        settings = self.settings
        key = cache_key(claim, settings.model)
        if not claim.redraft and await self._from_cache(claim, key):
            return
        if claim.claims > MAX_CLAIMS:
            await self._fall_back(claim, "The agent service failed on this one; the template stands.")
            return
        if claim.waited > settings.queue_seconds:
            await self._fall_back(claim, "It waited too long for an agent; the template stands.")
            return
        if await self.store.runs_today() >= settings.daily_runs:
            await self._fall_back(claim, "Today's agent budget is spent; the template stands.")
            return

        agent_run_id = uuid.uuid4().hex
        await self.store.start_run(agent_run_id, claim, key, settings.model, PROMPT_VERSION)
        job = Job(claim.run_id, claim.insight_id, claim.kind, claim.facts_version)
        try:
            drafted = await asyncio.wait_for(
                draft(job, self.client, self.mcp_url, settings.options), timeout=settings.deadline_seconds
            )
        except asyncio.CancelledError:
            log.info(
                "%s/%s: draft for facts version %d superseded", claim.run_id, claim.insight_id, claim.facts_version
            )
            await asyncio.shield(self.store.finish_run(agent_run_id, outcome="superseded"))
            raise
        except TimeoutError:
            log.info("%s/%s: no draft within %.0f s", claim.run_id, claim.insight_id, settings.deadline_seconds)
            await self.store.finish_run(agent_run_id, outcome="timeout")
            await self._fall_back(
                claim, f"No agent draft within {settings.deadline_seconds:.0f} s; the template stands."
            )
            return
        except Exception as exc:
            log.exception("agent run %s failed", agent_run_id)
            await self.store.finish_run(agent_run_id, outcome="error", error=f"{type(exc).__name__}: {exc}"[:2000])
            await self._fall_back(claim, "The agent failed on this one; the template stands.")
            return
        log.info(
            "%s/%s: %s after %d attempt(s), %d ms, %d tokens in, %d out",
            claim.run_id,
            claim.insight_id,
            "accepted" if drafted.outcome.accepted else "rejected",
            drafted.outcome.attempts,
            drafted.latency_ms,
            drafted.usage.input_tokens,
            drafted.usage.output_tokens,
        )
        await self._finish(claim, key, agent_run_id, drafted)

    async def _finish(self, claim: Claim, key: str, agent_run_id: str, drafted: Drafted) -> None:
        outcome = drafted.outcome
        await self.store.finish_run(
            agent_run_id,
            outcome="accepted" if outcome.accepted else "rejected",
            attempts=outcome.attempts,
            input_tokens=drafted.usage.input_tokens,
            output_tokens=drafted.usage.output_tokens,
            reasoning_tokens=drafted.usage.reasoning_tokens,
            latency_ms=drafted.latency_ms,
            problems=outcome.problems or None,
            tool_calls=drafted.log.calls,
            draft=outcome.draft.model_dump() if outcome.draft else None,
        )
        if not outcome.accepted or outcome.draft is None:
            await self._fall_back(claim, "The agent's draft failed the checks; the template stands.")
            return
        await self.store.cache(key, agent_run_id, outcome.draft, drafted.log.facts, drafted.log.events)
        provenance = {
            "source": "agent",
            "agent_run_id": agent_run_id,
            "model": self.settings.model,
            "prompt": PROMPT_VERSION,
            "attempts": outcome.attempts,
            "tools": sorted({call["name"] for call in drafted.log.calls}),
            "latency_ms": drafted.latency_ms,
            "checks": "passed",
            "cached": False,
        }
        await self._send(claim, await self.store.publish(claim, outcome.draft, drafted.log.facts, provenance))

    async def _from_cache(self, claim: Claim, key: str) -> bool:
        hit = await self.store.cached(key)
        if hit is None or check(hit.draft, hit.facts, hit.events):
            return False
        provenance = {
            "source": "agent",
            "agent_run_id": hit.agent_run_id,
            "model": self.settings.model,
            "prompt": PROMPT_VERSION,
            "checks": "passed",
            "cached": True,
        }
        await self._send(claim, await self.store.publish(claim, hit.draft, hit.facts, provenance))
        return True

    async def _fall_back(self, claim: Claim, note: str) -> None:
        await self._send(claim, await self.store.fall_back(claim, note))

    async def _send(self, claim: Claim, message: dict | None) -> None:
        if message is None:
            return
        try:
            await self.push.send(claim.run_id, message)
        except Exception:
            log.exception("push failed for %s/%s", claim.run_id, claim.insight_id)
