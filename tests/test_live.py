"""The live match model shared by the services: timeline, stats, state and the viewer contract."""

from __future__ import annotations

import json

import pytest

from footnote.live.contract import client_event
from footnote.live.match import Match, load_match
from footnote.live.state import RunState
from footnote.live.timeline import Timeline


@pytest.fixture(scope="module")
def showcase() -> Match:
    return load_match()


@pytest.fixture(scope="module")
def timeline(showcase: Match) -> Timeline:
    return Timeline.from_feed(showcase.feed)


def _final_state(showcase: Match) -> RunState:
    return RunState.rebuild(showcase.match_id, showcase.home_id, showcase.away_id, showcase.feed)


def test_replay_seconds_follow_the_match_clock_and_shorten_the_break(showcase: Match, timeline: Timeline) -> None:
    for m in showcase.feed:
        if m["type"] in ("match_info", "amendment"):
            continue
        assert timeline.replay_seconds(m["ts"]) == pytest.approx(timeline.at(m["period"], m["t"]), abs=1e-6)
    first_end = next(m for m in showcase.feed if m["type"] == "period_end" and m["period"] == 1)
    second_start = next(m for m in showcase.feed if m["type"] == "period_start" and m["period"] == 2)
    gap = timeline.replay_seconds(second_start["ts"]) - timeline.replay_seconds(first_end["ts"])
    assert gap == pytest.approx(timeline.half_time)


def test_moment_inverts_at(timeline: Timeline) -> None:
    for period, t in [(1, 0.0), (1, 1357.25), (1, timeline.first_half_end), (2, 0.0), (2, 2110.06)]:
        assert timeline.moment(timeline.at(period, t)) == (period, pytest.approx(t))
    assert timeline.moment(timeline.first_half_end + timeline.half_time / 2) is None


def test_jump_points_lead_in_without_crossing_a_period_start(timeline: Timeline) -> None:
    assert timeline.jump_point(1) == 0.0
    assert timeline.moment(timeline.jump_point(23)) == (1, 22 * 60 - 30)
    assert timeline.moment(timeline.jump_point(46)) == (2, 0.0)
    assert timeline.moment(timeline.jump_point(81)) == (2, 35 * 60 - 30)
    with pytest.raises(ValueError):
        timeline.jump_point(91)


def test_stats_at_full_time_match_the_feed(showcase: Match) -> None:
    feed = showcase.feed
    view = _final_state(showcase).stats.view()
    home, away = showcase.home_id, showcase.away_id
    assert view["score"] == next(m for m in feed if m["type"] == "match_end")["score"]

    def count(team: str, **match: object) -> int:
        return sum(1 for m in feed if m.get("team_id") == team and all(m.get(k) == v for k, v in match.items()))

    for team in (home, away):
        passes = [m for m in feed if m["type"] == "pass" and m["team_id"] == team and m["pass_type"] != "throw_in"]
        stats = view["teams"][team]
        assert stats["passes"] == len(passes)
        assert stats["passes_completed"] == sum(m["outcome"] == "complete" for m in passes)
        assert stats["corners"] == count(team, type="pass", pass_type="corner")
        assert stats["fouls"] == count(team, type="foul")
        assert stats["offsides"] == count(team, type="offside")
        assert stats["yellow_cards"] == count(team, type="card", card="yellow") + count(
            team, type="card", card="second_yellow"
        )
    assert view["teams"][home]["possession"] + view["teams"][away]["possession"] == pytest.approx(1.0, abs=0.002)


def test_a_goal_ruled_out_by_var_takes_its_shot_off_the_count(showcase: Match) -> None:
    feed = showcase.feed
    ruling = next(m for m in feed if m["type"] == "var_check" and m.get("decision") == "no_goal")
    goal = next(m for m in feed if m["event_id"] == ruling["goal_event_id"])
    shot = next(m for m in feed if m["event_id"] == goal["from_event_id"])
    state = RunState(showcase.match_id, showcase.home_id, showcase.away_id)
    before = None
    for m in feed:
        state.apply(m)
        if m["seq"] == shot["seq"]:
            before = state.stats.teams[shot["team_id"]].shots
        if m["seq"] == ruling["seq"]:
            break
    assert before is not None
    assert state.stats.teams[shot["team_id"]].shots == before - 1
    assert state.stats.score == ruling["score"]


def test_state_phases_and_key_events(showcase: Match) -> None:
    state = RunState(showcase.match_id, showcase.home_id, showcase.away_id)
    phases = []
    for m in showcase.feed:
        state.apply(m)
        if not phases or phases[-1] != state.phase:
            phases.append(state.phase)
    assert phases == ["pre_match", "first_half", "half_time", "second_half", "full_time"]
    types = {e["type"] for e in state.key_events}
    assert {"goal", "var_check", "amendment", "card", "substitution"} <= types
    assert all("freeze_frame" not in e for e in state.key_events)


def test_state_skips_a_redelivered_message_and_a_correction_leaves_the_clock(showcase: Match) -> None:
    state = RunState(showcase.match_id, showcase.home_id, showcase.away_id)
    amendment = next(m for m in showcase.feed if m["type"] == "amendment")
    for m in showcase.feed[: amendment["seq"] - 1]:
        assert state.apply(m)
    clock = dict(state.clock or {})
    assert not state.apply(showcase.feed[0])
    assert state.apply(amendment)
    assert state.clock == clock


def test_rebuilding_from_the_stored_feed_gives_the_same_view(showcase: Match) -> None:
    incremental = RunState(showcase.match_id, showcase.home_id, showcase.away_id)
    for m in showcase.feed:
        incremental.apply(m)
    assert _final_state(showcase).view() == incremental.view()


def test_every_pushed_event_fits_one_web_pubsub_message(showcase: Match) -> None:
    """Web PubSub bills outbound traffic in 2 KB units, so each event push should stay inside one.

    The SDK serialises with json.dumps defaults, and the service wraps each message for the client;
    1800 bytes leaves room for the wrapper.
    """
    state = RunState(showcase.match_id, showcase.home_id, showcase.away_id)
    timing = {"published_at": 1_800_000_000_000, "enqueued_at": 1_800_000_000_000, "processed_at": 1_800_000_000_000}
    largest = 0
    for m in showcase.feed:
        state.apply(m)
        message = {"type": "event", "run_id": "0" * 16, "event": client_event(m), "key": True}
        message |= state.live_fields() | {"timing": timing}
        largest = max(largest, len(json.dumps(message).encode()))
    assert largest <= 1800
