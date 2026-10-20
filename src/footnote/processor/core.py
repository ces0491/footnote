"""Processing a batch of messages from the feed hub.

Delivery is at least once. Each run's messages arrive in order (they share a partition), and a run's
state skips any message it has already applied. The stored feed is written before anything is
pushed, so viewers never see an event the store doesn't have. If the store can't be written, the run
is dropped from memory and the error propagates: Event Hubs redelivers from the last checkpoint and
the run's state is rebuilt from what was stored. A run met again, including through its `run_start`,
carries on from the stored feed.

A push that fails is logged and skipped. Viewers notice the gap in `seq` and fetch the snapshot.

A replayer that shuts down publishes `run_end` for its runs; one that crashes can't. `end_overdue`
ends any run still marked running whose next message is long past the time it was due, as failed,
so its viewers aren't left waiting for messages that will never come.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import groupby
from typing import Protocol

from footnote.live.analysis import Analysis
from footnote.live.contract import KIND_CONTROL, RunEndReason, client_event
from footnote.live.match import Match
from footnote.live.state import KEY_EVENT_TYPES, RunState
from footnote.live.timeline import Timeline

log = logging.getLogger(__name__)

# How late a run's next message may be before the run counts as abandoned: far beyond any delay on
# the way through Event Hubs, and beyond the time a restarted processor takes to catch up.
OVERDUE_MS = 5 * 60_000


@dataclass(frozen=True)
class Incoming:
    """One event from the feed hub, decoded."""

    run_id: str
    kind: str  # "feed" or "control"
    body: dict
    published_at: int  # epoch ms, from the replayer
    enqueued_at: int | None  # epoch ms, from Event Hubs
    backfill: bool = False


@dataclass(frozen=True)
class FeedRow:
    run_id: str
    message: dict
    published_at: int
    enqueued_at: int | None


class Store(Protocol):
    async def start_run(self, descriptor: dict) -> bool:
        """Record a new run; False if it was already on record."""
        ...

    async def end_run(self, run_id: str, reason: str) -> None: ...

    async def load_run(self, run_id: str) -> tuple[dict, list[dict]] | None:
        """The run's descriptor and its stored feed in seq order, or None for an unknown run."""
        ...

    async def save(self, rows: list[FeedRow], run_id: str, view: dict | None) -> None:
        """Store feed rows and, unless it is None, the run's state view, in one transaction."""
        ...

    async def running_runs(self) -> list[tuple[dict, int]]:
        """Each run still marked running: its descriptor and the seq its stored state reflects."""
        ...


class Push(Protocol):
    async def send(self, run_id: str, message: dict) -> None: ...


@dataclass
class LiveRun:
    descriptor: dict
    state: RunState


@dataclass
class _Pending:
    rows: list[FeedRow] = field(default_factory=list)
    outgoing: list[dict] = field(default_factory=list)


def _now_ms() -> int:
    return int(time.time() * 1000)


class Processor:
    def __init__(
        self,
        match: Match,
        store: Store,
        push: Push,
        now_ms: Callable[[], int] = _now_ms,
        analysis: Analysis | None = None,
    ) -> None:
        self.match = match
        self.analysis = analysis
        self.store = store
        self.push = push
        self.now_ms = now_ms
        self.runs: dict[str, LiveRun] = {}
        self._unknown: set[str] = set()
        # Each message's replay second, by seq - 1, which sets when a run publishes it.
        timeline = Timeline.from_feed(match.feed)
        self._replay = [timeline.replay_seconds(m["ts"]) for m in match.feed]

    async def handle(self, batch: list[Incoming]) -> None:
        for run_id, items in groupby(batch, key=lambda i: i.run_id):
            try:
                await self._handle_run(run_id, list(items))
            except Exception:
                # Rebuild from the store on redelivery rather than trust state the store may not have.
                self.runs.pop(run_id, None)
                raise

    async def _handle_run(self, run_id: str, items: list[Incoming]) -> None:
        pending = _Pending()
        for item in items:
            if item.kind == KIND_CONTROL:
                await self._flush(run_id, pending)
                await self._control(run_id, item)
                continue
            run = await self._run(run_id)
            if run is None:
                continue
            m = item.body
            if not run.state.apply(m):
                continue
            pending.rows.append(FeedRow(run_id, m, item.published_at, item.enqueued_at))
            if item.backfill:
                if m["seq"] == run.descriptor["backfill_seq"]:
                    pending.outgoing.append(self._snapshot(run))
                continue
            pending.outgoing.append(
                {
                    "type": "event",
                    "run_id": run_id,
                    "event": client_event(m),
                    "key": m["type"] in KEY_EVENT_TYPES,
                    **run.state.push_fields(),
                    "timing": {"published_at": item.published_at, "enqueued_at": item.enqueued_at},
                }
            )
        await self._flush(run_id, pending)

    async def _flush(self, run_id: str, pending: _Pending) -> None:
        if pending.rows:
            run = self.runs[run_id]
            # Viewers get a run's state only once its backfill is in. A view from partway through the
            # backfill would show the score from minutes before the jump point.
            backfilled = run.state.seq >= run.descriptor["backfill_seq"]
            await self.store.save(pending.rows, run_id, run.state.view() if backfilled else None)
            pending.rows = []
        for message in pending.outgoing:
            await self._send(run_id, message)
        pending.outgoing = []

    async def _send(self, run_id: str, message: dict) -> None:
        message.setdefault("timing", {})["processed_at"] = self.now_ms()
        try:
            await self.push.send(run_id, message)
        except Exception:
            log.exception("push failed for run %s (%s seq %s)", run_id, message["type"], message.get("seq"))

    async def _control(self, run_id: str, item: Incoming) -> None:
        kind = item.body["type"]
        if kind == "run_start":
            descriptor = item.body["run"]
            self._unknown.discard(run_id)
            if not await self.store.start_run(descriptor):
                # Seen before: a redelivery, or the hub read again after a restart. Carry on from the
                # stored feed rather than from an empty state.
                if run_id not in self.runs:
                    await self._run(run_id)
                return
            run = LiveRun(descriptor, self._new_state())
            self.runs[run_id] = run
            log.info(
                "run %s started at replay second %s, speed %s", run_id, descriptor["start_replay"], descriptor["speed"]
            )
            if descriptor["backfill_seq"] == 0:
                await self._send(run_id, self._snapshot(run))
        elif kind == "run_end":
            await self._end(run_id, item.body["reason"])
        else:
            log.warning("run %s: unknown control message %r", run_id, kind)

    async def _end(self, run_id: str, reason: RunEndReason) -> None:
        await self.store.end_run(run_id, reason)
        self.runs.pop(run_id, None)
        log.info("run %s ended: %s", run_id, reason)
        await self._send(run_id, {"type": "run_end", "run_id": run_id, "reason": reason})

    async def end_overdue(self) -> list[str]:
        """End as failed each run still marked running whose next message is OVERDUE_MS late."""
        now = self.now_ms()
        ended = []
        for descriptor, seq in await self.store.running_runs():
            if now - self._due_ms(descriptor, seq) > OVERDUE_MS:
                run_id = descriptor["run_id"]
                log.warning("run %s: the message after seq %d is overdue; ending the run as failed", run_id, seq)
                await self._end(run_id, "failed")
                ended.append(run_id)
        return ended

    def _due_ms(self, descriptor: dict, seq: int) -> float:
        """When the run should have published the message after `seq`, or its last once all are in."""
        replay = self._replay[min(seq, len(self._replay) - 1)]
        ahead = max(0.0, replay - descriptor["start_replay"]) / descriptor["speed"]
        return float(descriptor["started_at"]) + ahead * 1000

    async def _run(self, run_id: str) -> LiveRun | None:
        run = self.runs.get(run_id)
        if run is not None or run_id in self._unknown:
            return run
        loaded = await self.store.load_run(run_id)
        if loaded is None:
            # Started before this processor was reading the hub; nothing to rebuild from.
            log.warning("run %s: no run_start on record; skipping its messages", run_id)
            self._unknown.add(run_id)
            return None
        descriptor, feed = loaded
        state = RunState.rebuild(self.match.match_id, self.match.home_id, self.match.away_id, feed, self.analysis)
        run = LiveRun(descriptor, state)
        self.runs[run_id] = run
        log.info("run %s rebuilt from %d stored messages", run_id, len(feed))
        return run

    def _new_state(self) -> RunState:
        return RunState(self.match.match_id, self.match.home_id, self.match.away_id, self.analysis)

    def _snapshot(self, run: LiveRun) -> dict:
        return {"type": "snapshot", "run_id": run.descriptor["run_id"], "run": run.descriptor, **run.state.view()}
