"""The evidence the models read: attacking frames, tracking lookups and tags, pass inputs that don't
give the outcome away, and state evidence that never looks past its lag."""

from __future__ import annotations

import json

import numpy as np
import pytest

from footnote.generator.season import GeneratedMatch, physical_summary
from footnote.interpret import difficulty
from footnote.interpret.dataset import as_recorded, true_states
from footnote.interpret.frames import Frames
from footnote.interpret.physical import DISTANCE_KM, SPRINT_KMH, Physical, Tracking
from footnote.interpret.shape import per_second
from footnote.interpret.state import FEATURES, LABELS, MIRROR_LABELS, Shown, StateModel, StateTracker, mirror
from footnote.interpret.train import shown_states, smooth
from footnote.live.match import Match, data_dir, load_match


@pytest.fixture(scope="module")
def showcase() -> Match:
    return load_match()


@pytest.fixture(scope="module")
def tracking(showcase: Match) -> Tracking:
    return Tracking.load(data_dir() / "matches" / showcase.match_id / "tracking.npz")


@pytest.fixture(scope="module")
def physical(showcase: Match, tracking: Tracking) -> Physical:
    return Physical(tracking, showcase.home_id, showcase.away_id)


_SHAPES: dict[str, dict[int, np.ndarray]] = {}


def shape_of(m: Match) -> dict[int, np.ndarray]:
    if m.match_id not in _SHAPES:
        tr = Tracking.load(data_dir() / "matches" / m.match_id / "tracking.npz")
        _SHAPES[m.match_id] = per_second(tr, Frames.from_meta(m.meta))
    return _SHAPES[m.match_id]


def test_frames_follow_the_attacking_directions(showcase: Match) -> None:
    frames = Frames.from_meta(showcase.meta)
    assert frames.side(showcase.home_id) == 0 and frames.side(showcase.away_id) == 1 and frames.side("x") is None
    # Home attacks towards x = 105 first, then the sides change ends.
    assert frames.u(0, 1, 80.0) == 80.0 and frames.u(0, 2, 80.0) == pytest.approx(25.0)
    assert frames.u(1, 1, 80.0) == pytest.approx(25.0) and frames.u(1, 2, 80.0) == 80.0
    flipped = frames.to_frame(1, 1, np.array([[10.0, 5.0], [np.nan, np.nan]]))
    assert flipped[0].tolist() == [95.0, 63.0] and np.isnan(flipped[1]).all()


def test_tracking_lookups_land_on_the_frame_at_or_before(tracking: Tracking) -> None:
    f = tracking.frame(2, 600.04)
    assert f is not None and tracking.period[f] == 2 and tracking.t[f] == pytest.approx(600.0)
    assert tracking.frame(1, 0.0) == 0
    assert tracking.frame(3, 10.0) is None
    positions = tracking.positions(1, 30.0)
    assert positions is not None and positions.players.shape == (22, 2) and len(positions.player_ids) == 22


def test_distance_and_top_speed_agree_with_the_generators_summary(match: GeneratedMatch) -> None:
    """The live figures and the calibration's come from the same tracking by different code."""
    assert match.tracking is not None
    tr = as_recorded(match.tracking)
    meta = match.output.meta
    physical = Physical(tr, meta["home"]["id"], meta["away"]["id"])
    summary = physical_summary(match)["players"]
    last = len(tr) - 1
    for pid, expected in summary.items():
        distance, top = physical.player_at(last, pid) or (0.0, 0.0)
        # The file's whole centimetres add a little jitter to every step.
        assert distance * 1000 == pytest.approx(expected["distance"], rel=0.01)
        # The calibration averages a second forwards from each frame, the live figure backwards; the
        # windows differ only at the edges of a player's time on the pitch.
        assert top == pytest.approx(expected["top_speed"] * 3.6, abs=0.6)


def test_tags_mark_sprints_and_distance_once_each(physical: Physical) -> None:
    sprints = [t for t in physical.tags if t.kind == "sprint"]
    distance = [t for t in physical.tags if t.kind == "distance"]
    assert sprints and distance
    assert all(t.value > SPRINT_KMH for t in sprints)
    assert len({t.player_id for t in distance}) == len(distance)
    assert all(t.value == DISTANCE_KM for t in distance)
    records = [t.value for t in sprints if t.record]
    assert records == sorted(records) and records[0] == sprints[0].value
    # Revealed in order as the clock passes them, each exactly once.
    frames = sorted({physical.tracking.frame(t.period, t.t) for t in physical.tags})
    revealed, before = [], None
    for f in frames:
        revealed += physical.tags_between(before, f)
        before = f
    assert revealed == physical.tags


def test_a_pass_rating_ignores_where_a_cut_out_pass_ended(showcase: Match, tracking: Tracking) -> None:
    frames = Frames.from_meta(showcase.meta)
    m = next(m for m in showcase.feed if m["type"] == "pass" and m["outcome"] == "incomplete" and not m["cross"])
    positions = tracking.positions(m["period"], m["t"])
    x = difficulty.features(m, frames, positions)
    # Move the end point along the same line, as if it had been cut out earlier or later.
    dx, dy = m["end_x"] - m["x"], m["end_y"] - m["y"]
    moved = {**m, "end_x": m["x"] + 0.4 * dx, "end_y": m["y"] + 0.4 * dy}
    assert x is not None and len(x) == len(difficulty.FEATURES)
    assert np.allclose(difficulty.features(moved, frames, positions), x)
    cross = next(m for m in showcase.feed if m["type"] == "pass" and m["cross"])
    elsewhere = {**cross, "end_x": 52.5, "end_y": 34.0}
    positions = tracking.positions(cross["period"], cross["t"])
    assert np.allclose(difficulty.features(elsewhere, frames, positions), difficulty.features(cross, frames, positions))


def test_mirroring_swaps_the_sides(showcase: Match) -> None:
    tracker = StateTracker(Frames.from_meta(showcase.meta), shape_of(showcase), None, lag=5, collect=True)
    for m in showcase.feed:
        tracker.observe(m)
    x = np.array([r[3] for r in tracker.rows])
    assert x.shape[1] == len(FEATURES) and np.isfinite(x).all()
    assert np.allclose(mirror(mirror(x)), x)
    home = FEATURES.index("w45_home_share")
    away = FEATURES.index("w45_away_share")
    assert np.allclose(mirror(x)[:, home], x[:, away])
    assert [LABELS[MIRROR_LABELS[LABELS.index("control:home")]]] == ["control:away"]


def test_state_evidence_never_looks_past_its_lag(showcase: Match) -> None:
    """The evidence for a second must be the same whether or not later events have arrived."""
    frames = Frames.from_meta(showcase.meta)
    lag = 5
    full = StateTracker(frames, shape_of(showcase), None, lag=lag, collect=True)
    for m in showcase.feed:
        full.observe(m)
    cut = next(m for m in showcase.feed if m["period"] == 1 and m["t"] > 1500)
    partial = StateTracker(frames, shape_of(showcase), None, lag=lag, collect=True)
    for m in showcase.feed[: cut["seq"] - 1]:
        partial.observe(m)
    seen = {(p, s): x for p, s, _, x in partial.rows}
    assert max(s for _, s in seen) <= cut["t"] - lag
    for p, s, _, x in full.rows:
        if (p, s) in seen:
            assert np.array_equal(seen[(p, s)], x)


def test_every_second_of_play_gets_one_estimate_and_its_true_state(showcase: Match) -> None:
    tracker = StateTracker(Frames.from_meta(showcase.meta), shape_of(showcase), None, lag=5, collect=True)
    for m in showcase.feed:
        tracker.observe(m)
    ends = {m["period"]: m["t"] for m in showcase.feed if m["type"] == "period_end"}
    for period, end in ends.items():
        seconds = [s for p, s, _, _ in tracker.rows if p == period]
        assert seconds == list(range(int(end) + 1))
    resets = [(p, s) for p, s, r, _ in tracker.rows if r]
    goals = [(m["period"], m["t"]) for m in showcase.feed if m["type"] == "goal"]
    assert [p for p, _ in resets] == [p for p, _ in goals]
    assert all(s - 1 < t <= s for (_, s), (_, t) in zip(resets, goals, strict=True))
    answer = json.loads((data_dir() / "answer_key" / f"{showcase.match_id}.json").read_text(encoding="utf-8"))
    labels = true_states(answer, 1, np.arange(0, 600))
    first = answer["regimes"][0]
    assert LABELS[labels[0]] == first["label"]
    assert LABELS[labels[int(first["end"]) + 1]] == answer["regimes"][1]["label"]


def test_training_replays_the_live_estimate_exactly(showcase: Match) -> None:
    """The smoothing and hold are chosen on precomputed network outputs; they must follow the tracker."""
    rng = np.random.default_rng(7)
    n = len(FEATURES)
    model = StateModel(
        lag=5,
        mean=np.zeros(n),
        scale=np.ones(n),
        hidden=rng.normal(0, 0.3, (n, 6)),
        hidden_bias=np.zeros(6),
        coef=rng.normal(0, 1.0, (6, len(LABELS))),
        intercept=np.zeros(len(LABELS)),
        smoothing=0.7,
        hold=5,
    )
    tracker = StateTracker(Frames.from_meta(showcase.meta), shape_of(showcase), model, collect=True)
    estimates = [e for m in showcase.feed for e in tracker.observe(m)]
    period = np.array([r[0] for r in tracker.rows])
    restart = np.array([r[2] for r in tracker.rows])
    replayed = smooth(model.classify(np.array([r[3] for r in tracker.rows])), period, restart, model.smoothing)
    assert np.allclose(np.array([e.belief for e in estimates]), replayed)
    shown = np.array([e.shown for e in estimates])
    assert np.array_equal(shown, shown_states(replayed, period, restart, model.hold))
    # The hold steadies the label: it changes no more often than the likeliest state does.
    likeliest = replayed.argmax(axis=1)
    assert np.sum(shown[1:] != shown[:-1]) < np.sum(likeliest[1:] != likeliest[:-1])


def test_a_challenger_is_shown_once_it_has_led_for_the_hold() -> None:
    shown = Shown()
    assert shown.update(0, hold=3, restart=False) == 0
    assert [shown.update(2, 3, False) for _ in range(3)] == [0, 0, 2]
    # A challenger that loses the lead before the hold is up starts again from nothing.
    assert [shown.update(4, 3, False), shown.update(2, 3, False), shown.update(4, 3, False)] == [2, 2, 2]
    assert shown.update(1, 3, restart=True) == 1
    # A break is shown the moment it leads and dropped the moment it doesn't.
    away_break = LABELS.index("transition:away")
    assert [shown.update(away_break, 3, False), shown.update(1, 3, False)] == [away_break, 1]
