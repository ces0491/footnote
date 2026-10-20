"""The processor's core: state, storage and pushes for a run, with in-memory stand-ins for Azure."""

from __future__ import annotations

import pytest

from footnote.live.contract import KIND_CONTROL, KIND_FEED
from footnote.live.match import Match, load_match
from footnote.live.timeline import Timeline
from footnote.processor.core import OVERDUE_MS, FeedRow, Incoming, Processor
from footnote.replayer.schedule import plan

RUN_ID = "0123456789abcdef"


class MemoryStore:
    def __init__(self) -> None:
        self.runs: dict[str, dict] = {}
        self.status: dict[str, str] = {}
        self.feed: dict[str, dict[int, dict]] = {}
        self.views: dict[str, dict] = {}
        self.view_seqs: list[int] = []
        self.fail_saves = 0

    async def start_run(self, descriptor: dict) -> bool:
        if descriptor["run_id"] in self.runs:
            return False
        self.runs[descriptor["run_id"]] = descriptor
        self.status[descriptor["run_id"]] = "running"
        return True

    async def end_run(self, run_id: str, reason: str) -> None:
        if self.status.get(run_id) == "running":
            self.status[run_id] = reason

    async def load_run(self, run_id: str) -> tuple[dict, list[dict]] | None:
        if run_id not in self.runs:
            return None
        stored = self.feed.get(run_id, {})
        return self.runs[run_id], [stored[seq] for seq in sorted(stored)]

    async def save(self, rows: list[FeedRow], run_id: str, view: dict | None) -> None:
        if self.fail_saves:
            self.fail_saves -= 1
            raise ConnectionError("store unavailable")
        for row in rows:
            self.feed.setdefault(row.run_id, {}).setdefault(row.message["seq"], row.message)
        if view is not None:
            self.views[run_id] = view
            self.view_seqs.append(view["seq"])

    async def running_runs(self) -> list[tuple[dict, int]]:
        return [
            (self.runs[run_id], self.views.get(run_id, {}).get("seq", 0))
            for run_id, status in self.status.items()
            if status == "running"
        ]


class MemoryPush:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, run_id: str, message: dict) -> None:
        assert message["run_id"] == run_id
        self.sent.append(message)


@pytest.fixture(scope="module")
def showcase() -> Match:
    return load_match()


def _run_messages(showcase: Match, start_minute: int) -> tuple[dict, list[Incoming]]:
    """What the replayer would put on the hub for a run, in order."""
    timeline = Timeline.from_feed(showcase.feed)
    start = timeline.jump_point(start_minute)
    p = plan(showcase.feed, timeline, start, 1.0)
    descriptor = {
        "run_id": RUN_ID,
        "match_id": showcase.match_id,
        "speed": 1.0,
        "start_minute": start_minute,
        "start_replay": start,
        "started_at": 1_800_000_000_000,
        "backfill_seq": p.backfill_seq,
        "timeline": timeline.describe(),
    }
    items = [Incoming(RUN_ID, KIND_CONTROL, {"type": "run_start", "run": descriptor}, 1, 2)]
    items += [Incoming(RUN_ID, KIND_FEED, m, 3, 4, backfill=True) for m in p.backfill]
    items += [Incoming(RUN_ID, KIND_FEED, m, 5, 6) for step in p.steps for m in step.messages]
    items.append(Incoming(RUN_ID, KIND_CONTROL, {"type": "run_end", "run_id": RUN_ID, "reason": "finished"}, 7, 8))
    return descriptor, items


async def test_a_run_from_a_jump_point_snapshots_then_pushes_each_event(showcase: Match) -> None:
    descriptor, items = _run_messages(showcase, 81)
    store, push = MemoryStore(), MemoryPush()
    processor = Processor(showcase, store, push, now_ms=lambda: 9)
    for i in range(0, len(items), 50):
        await processor.handle(items[i : i + 50])

    assert push.sent[0]["type"] == "snapshot"
    snapshot = push.sent[0]
    assert snapshot["seq"] == descriptor["backfill_seq"] and snapshot["run"] == descriptor
    assert snapshot["score"] == {"home": 1, "away": 1}

    events = [m for m in push.sent if m["type"] == "event"]
    assert [m["seq"] for m in events] == list(range(descriptor["backfill_seq"] + 1, len(showcase.feed) + 1))
    assert all(m["timing"] == {"published_at": 5, "enqueued_at": 6, "processed_at": 9} for m in events)
    goal = next(m for m in events if m["event"]["type"] == "goal")
    assert goal["key"] and goal["score"] == {"home": 1, "away": 2}
    assert push.sent[-1] == {"type": "run_end", "run_id": RUN_ID, "reason": "finished", "timing": {"processed_at": 9}}

    assert sorted(store.feed[RUN_ID]) == list(range(1, len(showcase.feed) + 1))
    assert store.views[RUN_ID]["phase"] == "full_time" and store.status[RUN_ID] == "finished"
    assert processor.runs == {}


async def test_a_view_is_stored_only_once_the_backfill_is_in(showcase: Match) -> None:
    """A snapshot read while the backfill is still being written would show an earlier score."""
    descriptor, items = _run_messages(showcase, 81)
    store, push = MemoryStore(), MemoryPush()
    processor = Processor(showcase, store, push)
    for i in range(0, 1000, 200):  # partway through the backfill
        await processor.handle(items[i : i + 200])
    assert RUN_ID not in store.views and len(store.feed[RUN_ID]) == 999
    await processor.handle(items[1000:])
    assert store.view_seqs and min(store.view_seqs) >= descriptor["backfill_seq"]


async def test_redelivered_messages_are_neither_stored_nor_pushed_twice(showcase: Match) -> None:
    _, items = _run_messages(showcase, 31)
    store, push = MemoryStore(), MemoryPush()
    processor = Processor(showcase, store, push)
    head = items[:700]
    await processor.handle(head)
    pushed = len(push.sent)
    await processor.handle(head[400:])
    assert len(push.sent) == pushed


async def test_a_restarted_processor_rebuilds_the_run_from_the_store(showcase: Match) -> None:
    _, items = _run_messages(showcase, 1)
    store, push = MemoryStore(), MemoryPush()
    await Processor(showcase, store, push).handle(items[:900])
    restarted = Processor(showcase, store, push)
    await restarted.handle(items[900:])
    assert sorted(store.feed[RUN_ID]) == list(range(1, len(showcase.feed) + 1))
    final = [m for m in push.sent if m["type"] == "event"][-1]
    assert final["score"] == {"home": 1, "away": 2} and final["phase"] == "full_time"


async def test_reading_a_run_again_from_its_start_resumes_from_the_store(showcase: Match) -> None:
    """A new revision reading the hub from before it started meets run_start again."""
    _, items = _run_messages(showcase, 1)
    store, push = MemoryStore(), MemoryPush()
    await Processor(showcase, store, push).handle(items[:900])
    stored_seq = store.views[RUN_ID]["seq"]
    pushed_before = len(push.sent)
    await Processor(showcase, store, push).handle(items[:950])
    assert store.view_seqs == sorted(store.view_seqs)  # the stored view never went backwards
    repeated = [m for m in push.sent[pushed_before:] if m["type"] in ("event", "snapshot")]
    assert repeated and all(m["seq"] > stored_seq for m in repeated)


async def test_a_failed_write_drops_the_run_and_redelivery_recovers_it(showcase: Match) -> None:
    _, items = _run_messages(showcase, 1)
    store, push = MemoryStore(), MemoryPush()
    processor = Processor(showcase, store, push)
    await processor.handle(items[:300])
    store.fail_saves = 1
    with pytest.raises(ConnectionError):
        await processor.handle(items[300:400])
    assert RUN_ID not in processor.runs
    await processor.handle(items[300:400])  # Event Hubs redelivers from the last checkpoint
    assert sorted(store.feed[RUN_ID]) == list(range(1, items[399].body["seq"] + 1))
    pushed = [m["seq"] for m in push.sent if m["type"] == "event"]
    assert pushed == sorted(set(pushed))


async def test_messages_for_a_run_it_never_saw_start_are_skipped(showcase: Match) -> None:
    _, items = _run_messages(showcase, 1)
    store, push = MemoryStore(), MemoryPush()
    await Processor(showcase, store, push).handle(items[5:20])
    assert push.sent == [] and store.feed == {}


async def test_a_failed_push_does_not_stop_processing(showcase: Match) -> None:
    _, items = _run_messages(showcase, 1)

    class FlakyPush(MemoryPush):
        async def send(self, run_id: str, message: dict) -> None:
            if message.get("seq") == 10:
                raise TimeoutError("push timed out")
            await super().send(run_id, message)

    store, push = MemoryStore(), FlakyPush()
    await Processor(showcase, store, push).handle(items[:40])
    seqs = [m["seq"] for m in push.sent if m["type"] == "event"]
    assert 10 not in seqs and 11 in seqs
    assert 10 in store.feed[RUN_ID]


async def test_a_run_whose_replayer_went_quiet_is_ended_as_failed(showcase: Match) -> None:
    """A replayer that crashes sends no run_end. Once the run's next message is long overdue, its
    viewers are told it failed rather than left waiting."""
    descriptor, items = _run_messages(showcase, 81)
    head = items[:1600]  # run_start and the feed up to seq 1599, then nothing more
    store, push = MemoryStore(), MemoryPush()
    now = {"ms": 0}
    processor = Processor(showcase, store, push, now_ms=lambda: now["ms"])
    await processor.handle(head)

    following = showcase.feed[head[-1].body["seq"]]  # the message after the last one stored
    replay = Timeline.from_feed(showcase.feed).replay_seconds(following["ts"])
    due = int(descriptor["started_at"] + (replay - descriptor["start_replay"]) / descriptor["speed"] * 1000)
    now["ms"] = due + OVERDUE_MS - 1
    assert await processor.end_overdue() == []
    now["ms"] = due + OVERDUE_MS + 1
    assert await processor.end_overdue() == [RUN_ID]
    assert store.status[RUN_ID] == "failed" and processor.runs == {}
    assert push.sent[-1]["type"] == "run_end" and push.sent[-1]["reason"] == "failed"
    assert await processor.end_overdue() == []


async def test_a_finished_run_is_never_taken_for_abandoned(showcase: Match) -> None:
    _, items = _run_messages(showcase, 81)
    store, push = MemoryStore(), MemoryPush()
    processor = Processor(showcase, store, push, now_ms=lambda: 10**15)
    await processor.handle(items)
    assert await processor.end_overdue() == []
    assert store.status[RUN_ID] == "finished"
