"""Processing a batch of messages from the feed hub.

Delivery is at least once. Each run's messages arrive in order (they share a partition), and a run's
state skips any message it has already applied. The stored feed is written before anything is
pushed, so viewers never see an event the store doesn't have. If the store can't be written, the run
is dropped from memory and the error propagates: Event Hubs redelivers from the last checkpoint and
the run's state is rebuilt from what was stored. A run met again, including through its `run_start`,
carries on from the stored feed.

A message that can't be folded fails the same way every time it is read, so it isn't left to
redelivery, which would hold up its partition and every run on it until the hub's retention dropped
it. Its run keeps what came before it and is ended as failed, and its later messages are skipped. A
control message that can't be used is logged and skipped.

A push that fails, or takes longer than PUSH_SECONDS, is logged and skipped. Viewers notice the gap
in `seq` and fetch the snapshot.
Each event push is stored with its feed row, and the snapshot with the backfill's last row, so a
viewer whose stream runs behind live can fetch the pushes it needs to see the match as of its own
playback.

Insights (footnote.insights) are found as each message is folded. Their changes are stored in the
same transaction as the feed rows that caused them, and the store returns the pushes for them: each
carries the run's insight revision, so a viewer who misses one fetches the snapshot too. An insight
that wants an agent's draft is left pending for the agents service, which the store notifies.

A replayer that shuts down publishes `run_end` for its runs; one that crashes can't. `end_overdue`
ends any run still marked running whose next message is long past the time it was due, as failed,
so its viewers aren't left waiting for messages that will never come.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from itertools import groupby
from typing import Protocol, cast, get_args

from footnote.insights.book import Change
from footnote.live.analysis import Analysis
from footnote.live.contract import (
    KIND_CONTROL,
    PRODUCER_MODES,
    VIEWER_PATTERN,
    ProducerMode,
    RunEndReason,
    client_event,
    stoppage,
)
from footnote.live.match import Match
from footnote.live.state import KEY_EVENT_TYPES, RunState
from footnote.live.timeline import Timeline
from footnote.processor.push import PUSH_SECONDS

log = logging.getLogger(__name__)

# How late a run's next message may be before the run counts as abandoned: far beyond any delay on
# the way through Event Hubs, and beyond the time a restarted processor takes to catch up.
OVERDUE_MS = 5 * 60_000

# How long a replay is kept once it has ended, so a page opened from its link still shows it. After
# that the sweep deletes it, a few at a time, with its feed, state, graphics and stored pushes. The
# agents' drafts and the translations are cached apart from replays, so later replays still reuse
# them. Without this a script starting replays at the rate limit would fill the server's 32 GB.
KEEP_ENDED = timedelta(days=1)
DELETE_BATCH = 20

END_REASONS: frozenset[str] = frozenset(get_args(RunEndReason))
# What a run_start's descriptor must hold for the processor to follow the run.
DESCRIPTOR_FIELDS = ("run_id", "match_id", "speed", "start_replay", "started_at", "backfill_seq")


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
    push: dict | None = None  # what viewers were sent for it, timing aside: an event, or the snapshot


class Store(Protocol):
    async def start_run(self, descriptor: dict, viewer: str | None = None, producer: ProducerMode = "auto") -> bool:
        """Record a new run, who started it and how its graphics are approved; False if it was
        already on record."""
        ...

    async def end_run(self, run_id: str, reason: str) -> None: ...

    async def load_run(self, run_id: str) -> tuple[dict, list[dict]] | None:
        """The run's descriptor and its stored feed in seq order, or None for an unknown run."""
        ...

    async def save(self, rows: list[FeedRow], run_id: str, view: dict | None, changes: list[Change]) -> list[dict]:
        """Store feed rows, the run's state view unless it is None, and the insight changes the rows
        made, in one transaction. Returns the pushes for the changed insights, in revision order."""
        ...

    async def running_runs(self) -> list[tuple[dict, int]]:
        """Each run still marked running: its descriptor and the seq its stored state reflects."""
        ...

    async def delete_ended_runs(self, ended_before: timedelta, limit: int) -> int:
        """Delete up to `limit` runs that ended more than `ended_before` ago, oldest first, with what
        was stored for them; returns how many it deleted."""
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
    changes: list[Change] = field(default_factory=list)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _stored(push: dict) -> dict:
    """A push as it is kept with its feed row: the timing is the live delivery's own."""
    return {k: v for k, v in push.items() if k != "timing"}


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
        self._failed: set[str] = set()  # ended over a message that couldn't be folded
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
            if run_id in self._failed:
                return
            if item.kind == KIND_CONTROL:
                await self._flush(run_id, pending)
                await self._control(run_id, item)
                continue
            run = await self._run(run_id)
            if run is None:
                continue
            try:
                self._fold(run, item, pending)
            except Exception:
                log.exception(
                    "run %s: can't fold %s seq %s; ending the run as failed",
                    run_id,
                    item.body.get("type"),
                    item.body.get("seq"),
                )
                # What came before it stands; the state it left half-applied isn't stored as a view.
                await self._flush(run_id, pending, with_view=False)
                self._failed.add(run_id)
                await self._end(run_id, "failed")
                return
        await self._flush(run_id, pending)

    def _fold(self, run: LiveRun, item: Incoming, pending: _Pending) -> None:
        """Fold one feed message into the run; what it stores and pushes joins `pending` only once
        the whole message has been taken in."""
        m = item.body
        if not run.state.apply(m):
            return
        changes = run.state.insight_changes()
        outgoing: dict | None = None
        if not item.backfill:
            outgoing = {
                "type": "event",
                "run_id": run.descriptor["run_id"],
                "event": client_event(m),
                "key": m["type"] in KEY_EVENT_TYPES,
                "replay": round(self._replay[m["seq"] - 1], 2),
                "stoppage": stoppage(m),
                **run.state.push_fields(),
                "timing": {"published_at": item.published_at, "enqueued_at": item.enqueued_at},
            }
        elif m["seq"] == run.descriptor["backfill_seq"]:
            outgoing = self._snapshot(run)
        stored = None if outgoing is None else _stored(outgoing)
        pending.rows.append(FeedRow(run.descriptor["run_id"], m, item.published_at, item.enqueued_at, stored))
        pending.changes += changes
        if outgoing is not None:
            pending.outgoing.append(outgoing)

    async def _flush(self, run_id: str, pending: _Pending, *, with_view: bool = True) -> None:
        insights: list[dict] = []
        if pending.rows:
            run = self.runs[run_id]
            # Viewers get a run's state only once its backfill is in. A view from partway through the
            # backfill would show the score from minutes before the jump point.
            backfilled = with_view and run.state.seq >= run.descriptor["backfill_seq"]
            insights = await self.store.save(
                pending.rows, run_id, run.state.view() if backfilled else None, pending.changes
            )
            pending.rows, pending.changes = [], []
        for message in [*pending.outgoing, *insights]:
            await self._send(run_id, message)
        pending.outgoing = []

    async def _send(self, run_id: str, message: dict) -> None:
        message.setdefault("timing", {})["processed_at"] = self.now_ms()
        try:
            # Bounded: the batch waits on each push, and a hung one would hold up every run on the
            # partition until the replays were ended as overdue.
            await asyncio.wait_for(self.push.send(run_id, message), PUSH_SECONDS)
        except Exception:
            log.exception("push failed for run %s (%s seq %s)", run_id, message["type"], message.get("seq"))

    async def _control(self, run_id: str, item: Incoming) -> None:
        kind = item.body.get("type")
        if kind == "run_start":
            descriptor = item.body.get("run")
            if not isinstance(descriptor, dict) or any(f not in descriptor for f in DESCRIPTOR_FIELDS):
                log.error("run %s: skipping a run_start without a usable descriptor", run_id)
                return
            self._unknown.discard(run_id)
            viewer = item.body.get("viewer")
            if viewer is not None and (not isinstance(viewer, str) or not re.fullmatch(VIEWER_PATTERN, viewer)):
                log.warning("run %s: run_start names no usable viewer; nobody can produce it", run_id)
                viewer = None
            producer = item.body.get("producer", "auto")
            if producer not in PRODUCER_MODES:
                log.warning("run %s: run_start with producer %r; approving automatically", run_id, producer)
                producer = "auto"
            if not await self.store.start_run(descriptor, viewer, cast(ProducerMode, producer)):
                # Seen before: a redelivery, or the hub read again after a restart. Carry on from the
                # stored feed rather than from an empty state.
                if run_id not in self.runs:
                    await self._run(run_id)
                return
            run = LiveRun(descriptor, self._new_state(descriptor))
            self.runs[run_id] = run
            log.info(
                "run %s started at replay second %s, speed %s", run_id, descriptor["start_replay"], descriptor["speed"]
            )
            if descriptor["backfill_seq"] == 0:
                await self._send(run_id, self._snapshot(run))
        elif kind == "run_end":
            reason = item.body.get("reason")
            if reason not in END_REASONS:
                log.warning("run %s: run_end with reason %r; ending it as failed", run_id, reason)
                reason = "failed"
            await self._end(run_id, cast(RunEndReason, reason))
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

    async def delete_old_runs(self) -> int:
        """Delete replays that ended more than KEEP_ENDED ago, DELETE_BATCH at most, oldest first."""
        deleted = await self.store.delete_ended_runs(KEEP_ENDED, DELETE_BATCH)
        if deleted:
            log.info("deleted %d replays that ended over %.0f h ago", deleted, KEEP_ENDED.total_seconds() / 3600)
        return deleted

    def _due_ms(self, descriptor: dict, seq: int) -> float:
        """When the run should have published the message after `seq`, or its last once all are in."""
        replay = self._replay[min(seq, len(self._replay) - 1)]
        ahead = max(0.0, replay - descriptor["start_replay"]) / descriptor["speed"]
        return float(descriptor["started_at"]) + ahead * 1000

    async def _run(self, run_id: str) -> LiveRun | None:
        run = self.runs.get(run_id)
        if run is not None or run_id in self._unknown or run_id in self._failed:
            return run
        loaded = await self.store.load_run(run_id)
        if loaded is None:
            # Started before this processor was reading the hub; nothing to rebuild from.
            log.warning("run %s: no run_start on record; skipping its messages", run_id)
            self._unknown.add(run_id)
            return None
        descriptor, feed = loaded
        state = RunState.rebuild(
            self.match.match_id,
            self.match.home_id,
            self.match.away_id,
            feed,
            self.analysis,
            backfill_seq=int(descriptor["backfill_seq"]),
        )
        run = LiveRun(descriptor, state)
        self.runs[run_id] = run
        log.info("run %s rebuilt from %d stored messages", run_id, len(feed))
        return run

    def _new_state(self, descriptor: dict) -> RunState:
        return RunState(
            self.match.match_id,
            self.match.home_id,
            self.match.away_id,
            self.analysis,
            backfill_seq=int(descriptor["backfill_seq"]),
        )

    def _snapshot(self, run: LiveRun) -> dict:
        return {"type": "snapshot", "run_id": run.descriptor["run_id"], "run": run.descriptor, **run.state.view()}
