"""The replayer: scheduling a run, publishing it on time, stopping it, and the HTTP API."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from footnote.live.contract import KIND_CONTROL
from footnote.live.match import Match, load_match
from footnote.live.timeline import Timeline
from footnote.replayer.app import create_app
from footnote.replayer.publish import Envelope
from footnote.replayer.runs import RunManager
from footnote.replayer.schedule import plan


@pytest.fixture(scope="module")
def showcase() -> Match:
    return load_match()


@pytest.fixture(scope="module")
def timeline(showcase: Match) -> Timeline:
    return Timeline.from_feed(showcase.feed)


class RecordingPublisher:
    def __init__(self) -> None:
        self.sent: list[tuple[float, str, Envelope]] = []
        self.clock = lambda: 0.0

    async def send(self, run_id: str, envelopes: list[Envelope]) -> None:
        self.sent.extend((self.clock(), run_id, e) for e in envelopes)


class FakeTime:
    """A clock that sleeping moves forward, so a whole match replays instantly."""

    def __init__(self, start: float = 1_800_000_000.0) -> None:
        self.now = start

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds
        await asyncio.sleep(0)


def test_plan_splits_the_feed_at_the_jump_point(showcase: Match, timeline: Timeline) -> None:
    start = timeline.jump_point(31)
    p = plan(showcase.feed, timeline, start, speed=2.0)
    sent = p.backfill + [m for step in p.steps for m in step.messages]
    assert [m["seq"] for m in sent] == [m["seq"] for m in showcase.feed]
    assert all(timeline.replay_seconds(m["ts"]) < start for m in p.backfill)
    assert p.backfill_seq == p.backfill[-1]["seq"]
    offsets = [s.offset for s in p.steps]
    assert offsets == sorted(offsets) and len(set(offsets)) == len(offsets)
    last = timeline.replay_seconds(showcase.feed[-1]["ts"])
    assert offsets[-1] == pytest.approx((last - start) / 2.0)


def test_a_replay_from_kick_off_backfills_only_the_line_ups(showcase: Match, timeline: Timeline) -> None:
    p = plan(showcase.feed, timeline, timeline.jump_point(1), speed=1.0)
    assert [m["type"] for m in p.backfill] == ["match_info"]


async def test_a_run_publishes_start_backfill_events_on_time_and_end(showcase: Match, timeline: Timeline) -> None:
    fake = FakeTime()
    publisher = RecordingPublisher()
    publisher.clock = fake.clock
    manager = RunManager(showcase, timeline, publisher, clock=fake.clock, sleep=fake.sleep)
    run = await manager.start(start_minute=81, speed=4.0)
    task = manager.runs[run["run_id"]].task
    assert task is not None
    await task

    envelopes = [e for _, _, e in publisher.sent]
    assert envelopes[0].kind == KIND_CONTROL and envelopes[0].body["type"] == "run_start"
    assert envelopes[-1].body == {"type": "run_end", "run_id": run["run_id"], "reason": "finished"}
    feed = [e for e in envelopes if e.kind != KIND_CONTROL]
    assert [e.body["seq"] for e in feed] == [m["seq"] for m in showcase.feed]
    assert [e.body["seq"] for e in feed if e.backfill][-1] == run["backfill_seq"]

    started_at = run["started_at"] / 1000
    for at, _, envelope in publisher.sent:
        if envelope.kind == KIND_CONTROL or envelope.backfill:
            continue
        due = started_at + (timeline.replay_seconds(envelope.body["ts"]) - run["start_replay"]) / 4.0
        assert at == pytest.approx(due, abs=1e-6)
    assert manager.runs == {}


async def test_stopping_a_run_publishes_run_end(showcase: Match, timeline: Timeline) -> None:
    publisher = RecordingPublisher()
    manager = RunManager(showcase, timeline, publisher, start_delay=60.0)
    run = await manager.start(start_minute=60)
    await asyncio.sleep(0.05)
    assert await manager.stop(run["run_id"])
    assert publisher.sent[-1][2].body == {"type": "run_end", "run_id": run["run_id"], "reason": "stopped"}
    assert not await manager.stop(run["run_id"])


async def test_a_new_run_evicts_the_oldest_at_capacity(showcase: Match, timeline: Timeline) -> None:
    publisher = RecordingPublisher()
    manager = RunManager(showcase, timeline, publisher, max_runs=2, start_delay=60.0)
    first = await manager.start()
    second = await manager.start()
    third = await manager.start()
    assert set(manager.runs) == {second["run_id"], third["run_id"]}
    ends = [e.body for _, _, e in publisher.sent if e.body.get("type") == "run_end"]
    assert ends == [{"type": "run_end", "run_id": first["run_id"], "reason": "evicted"}]
    await manager.close()


async def test_a_run_past_its_time_limit_expires(showcase: Match, timeline: Timeline) -> None:
    fake = FakeTime()
    publisher = RecordingPublisher()
    manager = RunManager(showcase, timeline, publisher, ttl=600.0, clock=fake.clock, sleep=fake.sleep)
    run = await manager.start(start_minute=1)
    task = manager.runs[run["run_id"]].task
    assert task is not None
    await task
    assert publisher.sent[-1][2].body["reason"] == "expired"


def test_api_starts_lists_and_stops_runs(showcase: Match) -> None:
    publisher = RecordingPublisher()
    with TestClient(create_app(showcase, publisher)) as client:
        created = client.post("/runs", json={"start_minute": 23, "speed": 2})
        assert created.status_code == 201
        run = created.json()
        assert run["speed"] == 2.0 and run["start_minute"] == 23 and run["match_id"] == showcase.match_id
        assert set(run["timeline"]) == {"first_half_end", "half_time"}
        assert [r["run_id"] for r in client.get("/runs").json()] == [run["run_id"]]
        assert client.get(f"/runs/{run['run_id']}").json() == run
        assert client.delete(f"/runs/{run['run_id']}").status_code == 204
        assert client.get(f"/runs/{run['run_id']}").status_code == 404
        assert client.get("/healthz").json() == {"status": "ok", "runs": 0}


@pytest.mark.parametrize("body", [{"start_minute": 0}, {"start_minute": 91}, {"speed": 3}, {"seek": 5}])
def test_api_rejects_bad_requests(showcase: Match, body: dict) -> None:
    with TestClient(create_app(showcase, RecordingPublisher())) as client:
        assert client.post("/runs", json=body).status_code == 422
