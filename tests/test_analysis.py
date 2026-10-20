"""What the processor works out beyond counting, with the fitted models: pass difficulty, the match
state and its timeline, player lines and tags, and the pushes that carry them."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from footnote.interpret.state import StateModel
from footnote.live.analysis import Analysis, timeline_after
from footnote.live.contract import client_event, wire
from footnote.live.match import Match, load_match
from footnote.live.state import RunState

FIXTURE = Path(__file__).with_name("fixtures") / "state_timeline.json"


@pytest.fixture(scope="module")
def showcase() -> Match:
    return load_match()


@pytest.fixture(scope="module")
def analysis(showcase: Match) -> Analysis:
    return Analysis.load(showcase)


@pytest.fixture(scope="module")
def final(showcase: Match, analysis: Analysis) -> RunState:
    return RunState.rebuild(showcase.match_id, showcase.home_id, showcase.away_id, showcase.feed, analysis)


def test_the_timeline_rule_matches_the_browsers() -> None:
    """frontend/src/lib/live/run-reducer.test.ts folds the same estimates by the browser's rule."""
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    timeline: list[dict] = []
    for state in fixture["states"]:
        timeline = timeline_after(timeline, state)
    assert timeline == fixture["timeline"]


def test_a_run_rebuilt_from_its_feed_reaches_the_same_view(
    showcase: Match, analysis: Analysis, final: RunState
) -> None:
    incremental = RunState(showcase.match_id, showcase.home_id, showcase.away_id, analysis)
    for m in showcase.feed:
        incremental.apply(m)
    assert json.dumps(incremental.view()) == json.dumps(final.view())


def test_every_pass_gets_a_difficulty_and_crosses_rate_harder(showcase: Match, analysis: Analysis) -> None:
    ratings: dict[str, list[float]] = {"cross": [], "ground": []}
    for m in showcase.feed:
        if m["type"] != "pass":
            continue
        rating = analysis.pass_difficulty(m)
        assert rating is not None and 0.0 <= rating <= 1.0
        if m["cross"]:
            ratings["cross"].append(rating)
        elif m["height"] == "ground" and m["pass_type"] == "open_play":
            ratings["ground"].append(rating)
    assert np.mean(ratings["cross"]) > 2 * np.mean(ratings["ground"])


def test_the_state_estimate_runs_its_lag_behind_the_feed(showcase: Match, analysis: Analysis) -> None:
    lag = StateModel.load().lag
    state = RunState(showcase.match_id, showcase.home_id, showcase.away_id, analysis)
    for m in showcase.feed:
        state.apply(m)
        ms = state.live_fields()["match_state"]
        if ms is None or m["type"] in ("amendment", "period_end", "match_end") or ms["period"] != m["period"]:
            continue
        assert m["t"] - lag - 1 < ms["second"] <= m["t"] - lag
        assert 0.0 <= ms["confidence"] <= 1.0
        assert ms["on_top"]["home"] + ms["on_top"]["away"] <= 1.0 + 1e-9


def test_the_view_carries_the_timeline_players_and_tags(final: RunState, analysis: Analysis) -> None:
    view = final.view()
    timeline = view["state_timeline"]
    assert timeline and timeline[0]["period"] == 1 and timeline[-1]["period"] == 2
    assert all(a["end"] < b["start"] or a["period"] < b["period"] for a, b in zip(timeline, timeline[1:], strict=False))
    assert [t["player_id"] for t in view["tags"]] == [t.player_id for t in analysis.physical.tags]
    varlan = view["players"]["sal-10"]
    assert varlan["passes"] > 20 and 0.0 < varlan["difficulty"] < varlan["hardest"] <= 1.0
    assert 5.0 < varlan["distance_km"] < 14.0 and 20.0 < varlan["top_speed_kmh"] < 38.0
    home = view["teams"][final.home_id]
    assert home["top_shot_kmh"] is not None and home["distance_km"] > 50.0


def test_every_push_with_the_analysis_fits_one_web_pubsub_message(showcase: Match, analysis: Analysis) -> None:
    """As tests/test_live.py checks for the counts alone: 1800 bytes leaves room for the wrapper."""
    state = RunState(showcase.match_id, showcase.home_id, showcase.away_id, analysis)
    timing = {"published_at": 1_800_000_000_000, "enqueued_at": 1_800_000_000_000, "processed_at": 1_800_000_000_000}
    largest = 0
    for m in showcase.feed:
        state.apply(m)
        message = {"type": "event", "run_id": "0" * 16, "event": client_event(m), "key": True}
        message |= state.push_fields() | {"timing": timing}
        largest = max(largest, len(wire(message).encode()))
    assert largest <= 1800
