"""Training and test rows from generated matches.

Each match is generated in memory with its tracking. Its feed goes through the same code the
processor runs (`StateTracker`, `difficulty.features`) and the answer key supplies the labels: the
true state at every second and the true completion probability of every pass. Tracking is rounded
to whole centimetres first, as the tracking file stores it.

The split is by playing style. Matches involving a club from a held-out archetype are the test set,
so the models are scored on styles they were never fitted on.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from footnote.generator.league import League
from footnote.generator.season import Fixture, GeneratedMatch, generate_match
from footnote.generator.tracking import Tracking as GeneratedTracking
from footnote.interpret import difficulty
from footnote.interpret.frames import Frames
from footnote.interpret.physical import Tracking
from footnote.interpret.shape import per_second
from footnote.interpret.state import FEATURES, LABELS, StateModel, StateTracker

HELD_OUT_ARCHETYPES = ("wing_crossing", "direct_aerial")
# Training matches on these matchdays choose how the state estimate is steadied; the rest fit the models.
VALIDATION_MATCHDAYS = range(31, 39)


@dataclass
class PassRows:
    x: np.ndarray  # (n, len(difficulty.FEATURES))
    complete: np.ndarray  # (n,) 1 if the ball reached its target (offside included)
    truth: np.ndarray  # (n,) the answer key's completion probability
    side: np.ndarray  # (n,) 0 home, 1 away
    throw_in: np.ndarray  # (n,) bool


@dataclass
class StateRows:
    x: np.ndarray  # (n, len(state.FEATURES)) float32
    label: np.ndarray  # (n,) index into LABELS
    period: np.ndarray
    second: np.ndarray
    restart: np.ndarray  # True at the first second after a goal
    # The true state at every second of each period, whatever `every` was: transitions are counted on it.
    sequence: dict[int, np.ndarray]


@dataclass
class MatchRows:
    match_id: str
    home: str
    away: str
    split: str  # "fit", "validate" or "test"
    passes: PassRows
    state: StateRows | None


def split_of(league: League, fixture: Fixture) -> str:
    held = {c.spec.code for c in league.clubs if c.spec.archetype in HELD_OUT_ARCHETYPES}
    if fixture.home in held or fixture.away in held:
        return "test"
    return "validate" if fixture.matchday in VALIDATION_MATCHDAYS else "fit"


def as_recorded(tr: GeneratedTracking) -> Tracking:
    """The generator's tracking as the tracking file stores it: whole centimetres."""

    def cm(a: np.ndarray) -> np.ndarray:
        return (np.round(a.astype(np.float64) * 100.0) / 100.0).astype(np.float32)  # NaN stays NaN

    return Tracking(tr.period, tr.t, cm(tr.players), cm(tr.ball), tr.occupancy, list(tr.slot_players))


def true_states(answer_key: dict, period: int, seconds: np.ndarray) -> np.ndarray:
    """Index into LABELS of the true state at each second of a period."""
    segments = [r for r in answer_key["regimes"] if r["period"] == period]
    starts = np.array([r["start"] for r in segments])
    index = {label: i for i, label in enumerate(LABELS)}
    labels = np.array([index[r["label"]] for r in segments])
    at = np.clip(np.searchsorted(starts, seconds, side="right") - 1, 0, len(segments) - 1)
    return labels[at]


def pass_rows(gm: GeneratedMatch, frames: Frames, tracking: Tracking) -> PassRows:
    truth = gm.output.answer_key["events"]
    xs, complete, p_true, side, throw_in = [], [], [], [], []
    for m in gm.output.feed:
        if m["type"] != "pass":
            continue
        x = difficulty.features(m, frames, tracking.positions(int(m["period"]), float(m["t"])))
        if x is None:
            continue
        xs.append(x)
        complete.append(m["outcome"] in ("complete", "offside"))
        p_true.append(truth[m["event_id"]]["p_complete"])
        side.append(frames.side(m["team_id"]))
        throw_in.append(m["pass_type"] == "throw_in")
    return PassRows(
        x=np.array(xs),
        complete=np.array(complete, dtype=float),
        truth=np.array(p_true),
        side=np.array(side),
        throw_in=np.array(throw_in),
    )


def state_rows(gm: GeneratedMatch, frames: Frames, tracking: Tracking, lag: int, every: int = 1) -> StateRows:
    tracker = StateTracker(frames, per_second(tracking, frames), None, lag=lag, collect=True)
    for m in gm.output.feed:
        tracker.observe(m)
    every_second = np.array([(r[0], r[1]) for r in tracker.rows])
    sequence = {p: true_states(gm.output.answer_key, p, every_second[every_second[:, 0] == p, 1]) for p in (1, 2)}
    rows = tracker.rows[::every]
    period = np.array([r[0] for r in rows])
    second = np.array([r[1] for r in rows])
    label = np.zeros(len(rows), dtype=np.int64)
    for p in (1, 2):
        sel = period == p
        label[sel] = true_states(gm.output.answer_key, p, second[sel])
    return StateRows(
        x=np.array([r[3] for r in rows], dtype=np.float32),
        label=label,
        period=period,
        second=second,
        restart=np.array([r[2] for r in rows], dtype=bool),
        sequence=sequence,
    )


def generate(league: League, fixture: Fixture) -> tuple[GeneratedMatch, Frames, Tracking]:
    gm = generate_match(league, fixture, with_tracking=True)
    assert gm.tracking is not None
    return gm, Frames.from_meta(gm.output.meta), as_recorded(gm.tracking)


def match_rows(league: League, fixture: Fixture, lag: int, fit_every: int) -> MatchRows:
    """Pass rows for every match; state evidence for training matches (every `fit_every`th second
    for fitting, every second for validation)."""
    gm, frames, tracking = generate(league, fixture)
    split = split_of(league, fixture)
    state = None
    if split != "test":
        state = state_rows(gm, frames, tracking, lag, every=fit_every if split == "fit" else 1)
    return MatchRows(fixture.match_id, fixture.home, fixture.away, split, pass_rows(gm, frames, tracking), state)


@dataclass
class StateTrace:
    """The live estimate at every second of a match, beside the truth and two simpler guesses."""

    match_id: str
    home: str
    away: str
    belief: np.ndarray  # (seconds, states): the live estimate
    shown: np.ndarray  # the state a viewer is shown each second
    label: np.ndarray  # the true state
    period: np.ndarray
    second: np.ndarray
    classifier: np.ndarray  # the network's likeliest state each second, without smoothing
    rule: np.ndarray  # control for a side with 60% of the ball over two minutes, otherwise balanced


def possession_rule(x: np.ndarray) -> np.ndarray:
    """A commentator's rule of thumb from the same evidence, as a baseline."""
    share = x[:, FEATURES.index("w120_home_share")]
    out = np.zeros(len(x), dtype=np.int64)
    out[share >= 0.6] = LABELS.index("control:home")
    out[share <= 0.4] = LABELS.index("control:away")
    return out


def trace(league: League, fixture: Fixture, model: StateModel) -> StateTrace:
    """Run the live tracker with a fitted model over a match, as the processor would."""
    gm, frames, tracking = generate(league, fixture)
    return trace_feed(
        fixture.match_id, fixture.home, fixture.away, gm.output.feed, gm.output.answer_key, frames, tracking, model
    )


def trace_feed(
    match_id: str,
    home: str,
    away: str,
    feed: list[dict],
    answer_key: dict,
    frames: Frames,
    tracking: Tracking,
    model: StateModel,
) -> StateTrace:
    tracker = StateTracker(frames, per_second(tracking, frames), model, collect=True)
    estimates = [e for m in feed for e in tracker.observe(m)]
    period = np.array([e.period for e in estimates])
    second = np.array([e.second for e in estimates])
    label = np.zeros(len(estimates), dtype=np.int64)
    for p in (1, 2):
        sel = period == p
        label[sel] = true_states(answer_key, p, second[sel])
    x = np.array([r[3] for r in tracker.rows])
    return StateTrace(
        match_id,
        home,
        away,
        belief=np.array([e.belief for e in estimates]),
        shown=np.array([e.shown for e in estimates]),
        label=label,
        period=period,
        second=second,
        classifier=model.classify(x).argmax(axis=1),
        rule=possession_rule(x),
    )
