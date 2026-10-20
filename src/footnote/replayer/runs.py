"""Running replays: one asyncio task per run, publishing its plan on time."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from footnote.live.contract import KIND_CONTROL, RunEndReason
from footnote.live.match import Match
from footnote.live.timeline import Timeline
from footnote.replayer.publish import Envelope, Publisher
from footnote.replayer.schedule import Plan, plan

log = logging.getLogger(__name__)

MAX_RUNS = 6  # concurrent replays; Web PubSub's free tier allows 20 connections in all
RUN_TTL = 2 * 60 * 60.0  # wall seconds; a full match at normal speed fits
START_DELAY = 2.0  # wall seconds between the request and the first live message, for the backfill


@dataclass
class ActiveRun:
    descriptor: dict
    plan: Plan
    viewer: str | None = None  # who started it; kept here, never in the descriptor everyone can read
    task: asyncio.Task | None = None
    stop_reason: RunEndReason | None = None
    created: float = field(default_factory=time.monotonic)


class RunManager:
    def __init__(
        self,
        match: Match,
        timeline: Timeline,
        publisher: Publisher,
        *,
        max_runs: int = MAX_RUNS,
        ttl: float = RUN_TTL,
        start_delay: float = START_DELAY,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.match = match
        self.timeline = timeline
        self.publisher = publisher
        self.max_runs = max_runs
        self.ttl = ttl
        self.start_delay = start_delay
        self.clock = clock
        self.sleep = sleep
        self.runs: dict[str, ActiveRun] = {}

    async def start(self, start_minute: int = 1, speed: float = 1.0, viewer: str | None = None) -> dict:
        # A viewer follows one replay at a time: their new one replaces the last, so trying the jump
        # points in turn never pushes anyone else's replay out. Only then is the oldest evicted.
        if viewer is not None:
            for previous in [r for r in self.runs.values() if r.viewer == viewer]:
                await self.stop(previous.descriptor["run_id"], reason="stopped")
        while len(self.runs) >= self.max_runs:
            oldest = min(self.runs.values(), key=lambda r: r.created)
            log.info("at %d runs; evicting %s", self.max_runs, oldest.descriptor["run_id"])
            await self.stop(oldest.descriptor["run_id"], reason="evicted")
        start_replay = self.timeline.jump_point(start_minute)
        run_plan = plan(self.match.feed, self.timeline, start_replay, speed)
        now = self.clock()
        descriptor = {
            "run_id": secrets.token_hex(8),
            "match_id": self.match.match_id,
            "speed": speed,
            "start_minute": start_minute,
            "start_replay": start_replay,
            "created_at": int(now * 1000),
            "started_at": int((now + self.start_delay) * 1000),
            "backfill_seq": run_plan.backfill_seq,
            "last_seq": self.match.feed[-1]["seq"],
            "timeline": self.timeline.describe(),
        }
        run = ActiveRun(descriptor, run_plan, viewer)
        self.runs[descriptor["run_id"]] = run
        run.task = asyncio.create_task(self._play(run), name=f"run-{descriptor['run_id']}")
        return descriptor

    async def stop(self, run_id: str, reason: RunEndReason = "stopped") -> bool:
        run = self.runs.get(run_id)
        if run is None or run.task is None:
            return False
        run.stop_reason = reason
        run.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await run.task
        if run_id in self.runs:
            # Cancelled before its task first ran, so _play never got to clean up.
            await self._finish(run_id, reason)
        return True

    async def close(self) -> None:
        for run_id in list(self.runs):
            await self.stop(run_id)

    async def _finish(self, run_id: str, reason: RunEndReason) -> None:
        self.runs.pop(run_id, None)
        end = Envelope({"type": "run_end", "run_id": run_id, "reason": reason}, KIND_CONTROL)
        try:
            await asyncio.shield(self.publisher.send(run_id, [end]))
        except Exception:
            log.exception("run %s: could not publish run_end", run_id)
        log.info("run %s ended: %s", run_id, reason)

    async def _play(self, run: ActiveRun) -> None:
        run_id = run.descriptor["run_id"]
        started_at = run.descriptor["started_at"] / 1000
        reason: RunEndReason = "finished"
        try:
            await self.publisher.send(run_id, [Envelope({"type": "run_start", "run": run.descriptor}, KIND_CONTROL)])
            if run.plan.backfill:
                await self.publisher.send(run_id, [Envelope(m, backfill=True) for m in run.plan.backfill])
            for step in run.plan.steps:
                delay = started_at + step.offset - self.clock()
                if delay > 0:
                    await self.sleep(delay)
                if self.clock() - started_at > self.ttl:
                    reason = "expired"
                    break
                await self.publisher.send(run_id, [Envelope(m) for m in step.messages])
        except asyncio.CancelledError:
            reason = run.stop_reason or "stopped"
            raise
        except Exception:
            log.exception("run %s failed", run_id)
            reason = "failed"
        finally:
            await self._finish(run_id, reason)
