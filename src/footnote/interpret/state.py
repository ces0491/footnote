"""The hidden match state, estimated live from the events and the tracking, a few seconds behind play.

At any moment a match is in one of eight states: one side in control, one side applying pressure,
one side breaking in transition, chaos, or balanced (docs/data.md describes how the generator
plays them). The feed never names the state; the events and the players' movement are the evidence.

Every second of play gets a vector of evidence over windows of 15 seconds to two minutes: from the
events, each side's share of the ball, where it has the ball and wins it back, how fast it moves
the ball forward, its passing, crosses, shots, long balls and pressing, and how often the ball
changes hands; from the tracking, how high each side's block stands, where its back and front lines
are, how wide it spreads and how fast its players are moving (shape.py); and how recently each
side won the ball and how far it has taken it since. The windows reach `lag` seconds past the second
being estimated, so the estimate for a second is ready `lag` seconds after it.

A small neural network (one hidden layer of tanh units under a softmax) turns the evidence into the
chance of each state. The live estimate is an exponential average of those chances, which restarts
at each kick-off and after a goal, when a new state begins. The state a viewer is shown changes only
once another has led the estimate for `hold` seconds in a row, so the label doesn't flicker between
two close states; a break, which lasts seconds, is shown and dropped at once.

`StateTracker` runs it over a feed one message at a time. Training runs the same code over
generated feeds, so the processor sees exactly the evidence the model was fitted on.
"""

from __future__ import annotations

import bisect
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from footnote.interpret.frames import LENGTH, Frames
from footnote.interpret.shape import COLUMNS, SHAPE_GLOBAL, SHAPE_SIDE

PARAMS = Path(__file__).with_name("params") / "state.json"

LABELS = (
    "balanced",
    "chaos",
    "control:home",
    "control:away",
    "pressure:home",
    "pressure:away",
    "transition:home",
    "transition:away",
)
# The same state seen with home and away swapped.
MIRROR_LABELS = (0, 1, 3, 2, 5, 4, 7, 6)
SIDE_OF_LABEL = (None, None, 0, 1, 0, 1, 0, 1)

WINDOWS = (15, 45, 120)  # seconds looked back over, before the lag
REGAIN_CAUSES = frozenset({"interception", "recovery", "duel", "tackle", "claim", "save"})

# Per side and second: counts and sums the windows add up.
_SIDE_AGG = (
    "onball",
    "onball_u",
    "final_third",
    "own_third",
    "passes",
    "passes_ok",
    "long",
    "progress",
    "crosses",
    "shots",
    "defending",
    "defending_u",
    "pressing",
    "pressing_u",
    "regains",
    "regains_u",
    "fouls",
    "carries",
)
_GLOBAL_AGG = ("changes", "stoppages", "events")
_A = {name: i for i, name in enumerate(_SIDE_AGG)}
_NA = len(_SIDE_AGG)
_COLS = 2 * _NA + len(_GLOBAL_AGG)
_G = {name: 2 * _NA + i for i, name in enumerate(_GLOBAL_AGG)}

_SIDE_FEATURES = (
    "share",
    "territory",
    "final_third",
    "own_third",
    "pass_rate",
    "pass_accuracy",
    "long_share",
    "progress_rate",
    "cross_rate",
    "shot_rate",
    "defending_rate",
    "defending_height",
    "pressing_rate",
    "pressing_height",
    "regain_rate",
    "regain_height",
    "foul_rate",
    "carry_rate",
)
_GLOBAL_FEATURES = ("change_rate", "stoppage_rate", "event_rate")
_SEQ_FEATURES = ("since_regain", "regain_height", "run_since_regain", "passes_since_regain", "on_ball", "spell")


def _feature_names() -> tuple[tuple[str, ...], np.ndarray, np.ndarray]:
    names: list[str] = []
    mirror: list[int] = []
    sign: list[float] = []

    def block(prefix: str, items: tuple[str, ...]) -> None:
        base = len(names)
        n = len(items)
        for side in (0, 1):
            for item in items:
                names.append(f"{prefix}{'home' if side == 0 else 'away'}_{item}")
        for side in (0, 1):
            for j in range(n):
                mirror.append(base + (1 - side) * n + j)
                sign.append(1.0)

    for w in WINDOWS:
        block(f"w{w}_", _SIDE_FEATURES)
        for item in _GLOBAL_FEATURES:
            mirror.append(len(names))
            sign.append(1.0)
            names.append(f"w{w}_{item}")
        block(f"w{w}_shape_", SHAPE_SIDE)
        for item in SHAPE_GLOBAL:
            mirror.append(len(names))
            sign.append(1.0)
            names.append(f"w{w}_shape_{item}")
    block("", _SEQ_FEATURES)
    for item, flips in (("minute", False), ("since_restart", False), ("goal_diff", True), ("late_goal_diff", True)):
        mirror.append(len(names))
        sign.append(-1.0 if flips else 1.0)
        names.append(item)
    return tuple(names), np.array(mirror), np.array(sign)


FEATURES, MIRROR_INDEX, MIRROR_SIGN = _feature_names()


def mirror(x: np.ndarray) -> np.ndarray:
    """Evidence with home and away swapped, for rows of x."""
    return x[..., MIRROR_INDEX] * MIRROR_SIGN


@dataclass
class _Sequence:
    """What each side has done since it last won the ball, as of a moment in the period."""

    regain_t: list[float | None] = field(default_factory=lambda: [None, None])
    regain_u: list[float] = field(default_factory=lambda: [0.0, 0.0])
    best_u: list[float] = field(default_factory=lambda: [0.0, 0.0])
    passes: list[int] = field(default_factory=lambda: [0, 0])
    possession: int | None = None
    possession_t: float = 0.0


class StateFeatures:
    """Per-second evidence for one match, built from its feed in order."""

    CAPACITY = 4000  # seconds in a period, grown if a period runs longer

    def __init__(self, frames: Frames, lag: int, shape: dict[int, np.ndarray]) -> None:
        self.frames = frames
        self.lag = lag
        self.shape = shape
        self.period = 0
        self._bins = np.zeros((self.CAPACITY, _COLS))
        self._cum = np.zeros((self.CAPACITY + 1, _COLS))
        self._cum_upto = 0
        self._shape_cum = np.zeros((1, COLUMNS))
        self._events: list[tuple[float, dict]] = []  # this period's events, in order, for _Sequence
        self._cursor = 0
        self._seq = _Sequence()
        self._score_times: list[float] = []
        self._score_diffs: list[int] = []
        self._goals: list[float] = []  # this period's goal times

    def start_period(self, period: int, score_diff: int) -> None:
        self.period = period
        self._bins[:] = 0.0
        self._cum[:] = 0.0
        self._cum_upto = 0
        seconds = self.shape[period]
        self._shape_cum = np.concatenate([np.zeros((1, COLUMNS)), np.cumsum(seconds, axis=0)])
        self._events = []
        self._cursor = 0
        self._seq = _Sequence()
        self._score_times = [0.0]
        self._score_diffs = [score_diff]
        self._goals = []

    def _shape_window(self, start: float, stop: float) -> np.ndarray:
        """Mean shape over the seconds [start, stop) that the tracking has; the last one if none."""
        n = len(self._shape_cum) - 1
        c = min(max(int(stop), 1), n)
        a = min(max(int(start), 0), c - 1)
        return (self._shape_cum[c] - self._shape_cum[a]) / (c - a)

    def score_diff(self, t: float) -> int:
        """Home goals minus away goals as the feed had it before `t`."""
        i = bisect.bisect_left(self._score_times, t) - 1
        return self._score_diffs[max(i, 0)]

    def add(self, m: dict) -> None:
        t = float(m["t"])
        kind = m["type"]
        if kind == "goal":
            self._goals.append(t)
        if isinstance(m.get("score"), dict) and kind in ("goal", "var_check"):
            self._score_times.append(t)
            self._score_diffs.append(int(m["score"]["home"]) - int(m["score"]["away"]))
        side = self.frames.side(m.get("team_id"))
        b = int(t)
        if b >= len(self._bins):
            self._grow(b + 1)
        row = self._bins[b]
        if kind in ("ball_out", "offside", "foul"):
            row[_G["stoppages"]] += 1
        if side is None or "x" not in m:
            return
        u = self.frames.u(side, self.period, float(m["x"]))
        a = side * _NA
        counted = True
        if kind in ("pass", "carry", "shot"):
            row[a + _A["onball"]] += 1
            row[a + _A["onball_u"]] += u
            row[a + _A["final_third"]] += u > 70.0
            row[a + _A["own_third"]] += u < 35.0
            if kind == "pass":
                row[a + _A["passes"]] += 1
                row[a + _A["passes_ok"]] += m["outcome"] in ("complete", "offside")
                row[a + _A["long"]] += m["height"] == "high" and float(m["length"]) > 30.0
                row[a + _A["crosses"]] += bool(m.get("cross"))
                end_u = self.frames.u(side, self.period, float(m["end_x"]))
                row[a + _A["progress"]] += max(end_u - u, 0.0)
            elif kind == "carry":
                row[a + _A["carries"]] += 1
                row[a + _A["progress"]] += max(self.frames.u(side, self.period, float(m["end_x"])) - u, 0.0)
            else:
                row[a + _A["shots"]] += 1
        elif kind in ("tackle", "interception", "ball_recovery", "block", "duel", "goalkeeper", "clearance"):
            row[a + _A["defending"]] += 1
            row[a + _A["defending_u"]] += u
            if kind == "clearance":
                row[a + _A["long"]] += 1
        elif kind == "pressure":
            row[a + _A["pressing"]] += 1
            row[a + _A["pressing_u"]] += u
        elif kind == "possession_change":
            counted = False
            if m.get("cause") in REGAIN_CAUSES:
                row[a + _A["regains"]] += 1
                row[a + _A["regains_u"]] += u
                row[_G["changes"]] += 1
        elif kind == "foul":
            row[a + _A["fouls"]] += 1
        else:
            counted = False
        if counted:
            row[_G["events"]] += 1
        if kind in ("pass", "carry", "shot", "possession_change"):
            self._events.append((t, m))

    def _grow(self, needed: int) -> None:
        size = max(needed, 2 * len(self._bins))
        bins = np.zeros((size, _COLS))
        bins[: len(self._bins)] = self._bins
        cum = np.zeros((size + 1, _COLS))
        cum[: len(self._cum)] = self._cum
        self._bins, self._cum = bins, cum

    def _window(self, start: float, stop: float) -> np.ndarray:
        """Sums over the seconds [start, stop), whose events are all in."""
        a, c = max(int(start), 0), max(int(stop), 0)
        if c > len(self._bins):
            self._grow(c)
        if c > self._cum_upto:
            self._cum[self._cum_upto + 1 : c + 1] = self._cum[self._cum_upto] + np.cumsum(
                self._bins[self._cum_upto : c], axis=0
            )
            self._cum_upto = c
        return self._cum[c] - self._cum[a]

    def _advance(self, until: float) -> _Sequence:
        """Fold this period's on-ball events before `until` into the per-side sequence state."""
        seq = self._seq
        while self._cursor < len(self._events) and self._events[self._cursor][0] < until:
            t, m = self._events[self._cursor]
            self._cursor += 1
            side = self.frames.side(m.get("team_id"))
            if side is None:
                continue
            u = self.frames.u(side, self.period, float(m["x"]))
            if m["type"] == "possession_change":
                if seq.possession != side:
                    seq.possession, seq.possession_t = side, t
                if m.get("cause") in REGAIN_CAUSES:
                    seq.regain_t[side], seq.regain_u[side], seq.best_u[side] = t, u, u
                    seq.passes[side] = 0
                continue
            if seq.regain_t[side] is not None:
                seq.best_u[side] = max(seq.best_u[side], u)
                seq.passes[side] += m["type"] == "pass"
        return seq

    def vector(self, s: int, end: float | None = None) -> np.ndarray:
        """Evidence for second `s`; `end` is the period's end when the period is over."""
        horizon = s + self.lag if end is None else min(s + self.lag, end)
        out: list[float] = []
        for w in WINDOWS:
            start = max(s - w, 0)
            dur = max(horizon - start, 1.0)
            agg = self._window(start, np.ceil(horizon) if end is not None else horizon)
            per_min = 60.0 / dur
            for side in (0, 1):
                out += _side_features(agg[side * _NA : (side + 1) * _NA], agg[(1 - side) * _NA :][:_NA], dur)
            out += [float(agg[_G[name]]) * per_min for name in _GLOBAL_AGG]
            out += self._shape_window(start, np.ceil(horizon) if end is not None else horizon).tolist()
        seq = self._advance(horizon)
        for side in (0, 1):
            since = seq.regain_t[side]
            if since is None:
                out += [1.0, 0.5, 0.0, 0.0]
            else:
                out += [
                    min((horizon - since) / 60.0, 1.0),
                    seq.regain_u[side] / LENGTH,
                    float(np.clip((seq.best_u[side] - seq.regain_u[side]) / 50.0, 0.0, 1.0)),
                    min(seq.passes[side] / 10.0, 1.0),
                ]
        for side in (0, 1):
            on = seq.possession == side
            out += [float(on), min((horizon - seq.possession_t) / 60.0, 1.0) if on else 0.0]
        # Reorder the sequence block side by side, to match FEATURES: four per side, then two per side.
        seq_block = out[-12:]
        out[-12:] = seq_block[0:4] + seq_block[8:10] + seq_block[4:8] + seq_block[10:12]
        minute = s / 60.0 + (45.0 if self.period == 2 else 0.0)
        restart = max([0.0] + [g for g in self._goals if g < horizon])
        diff = float(np.clip(self.score_diff(horizon), -3, 3)) / 3.0
        out += [minute / 90.0, min((horizon - restart) / 120.0, 1.0), diff, max(minute - 60.0, 0.0) / 30.0 * diff]
        return np.array(out)


def _side_features(own: np.ndarray, other: np.ndarray, dur: float) -> list[float]:
    """One side's evidence over a window of `dur` seconds, from its sums and the opponent's."""

    def g(name: str) -> float:
        return float(own[_A[name]])

    def mean_height(name: str, count: str) -> float:
        return g(name) / g(count) / LENGTH if g(count) else 0.5

    per_min = 60.0 / dur
    onball, passes = g("onball"), g("passes")
    return [
        (onball + 1.0) / (onball + float(other[_A["onball"]]) + 2.0),
        mean_height("onball_u", "onball"),
        g("final_third") / (onball + 1.0),
        g("own_third") / (onball + 1.0),
        passes * per_min,
        (g("passes_ok") + 1.0) / (passes + 2.0),
        g("long") / (passes + 1.0),
        g("progress") / dur,
        g("crosses") * per_min,
        g("shots") * per_min,
        g("defending") * per_min,
        mean_height("defending_u", "defending"),
        g("pressing") * per_min,
        mean_height("pressing_u", "pressing"),
        g("regains") * per_min,
        mean_height("regains_u", "regains"),
        g("fouls") * per_min,
        g("carries") * per_min,
    ]


@dataclass(frozen=True)
class StateModel:
    lag: int
    mean: np.ndarray  # (features,)
    scale: np.ndarray  # (features,)
    hidden: np.ndarray  # (features, units)
    hidden_bias: np.ndarray  # (units,)
    coef: np.ndarray  # (units, states)
    intercept: np.ndarray  # (states,)
    smoothing: float  # weight the running estimate keeps each second
    hold: int  # seconds a new state must lead before the shown state changes

    @classmethod
    def load(cls, path: Path = PARAMS) -> StateModel:
        p = json.loads(path.read_text(encoding="utf-8"))
        if tuple(p["features"]) != FEATURES or tuple(p["labels"]) != LABELS:
            raise ValueError(f"{path}: fitted on different features; refit with python -m footnote.interpret")
        return cls(
            lag=int(p["lag"]),
            mean=np.array(p["mean"]),
            scale=np.array(p["scale"]),
            hidden=np.array(p["hidden"]),
            hidden_bias=np.array(p["hidden_bias"]),
            coef=np.array(p["coef"]),
            intercept=np.array(p["intercept"]),
            smoothing=float(p["smoothing"]),
            hold=int(p["hold"]),
        )

    def classify(self, x: np.ndarray) -> np.ndarray:
        """The network's chance of each state for rows of x, before smoothing."""
        h = np.tanh(((np.atleast_2d(x) - self.mean) / self.scale) @ self.hidden + self.hidden_bias)
        z = h @ self.coef + self.intercept
        z -= z.max(axis=1, keepdims=True)
        e = np.exp(z)
        return e / e.sum(axis=1, keepdims=True)

    def step(self, belief: np.ndarray | None, x: np.ndarray, restart: bool = False) -> np.ndarray:
        """One second: the running estimate before it (None at a restart) and the evidence for it."""
        p = self.classify(x)[0]
        if belief is None or restart:
            return p
        return self.smoothing * belief + (1.0 - self.smoothing) * p


BREAKS = frozenset(i for i, label in enumerate(LABELS) if label.startswith("transition"))


@dataclass
class Shown:
    """The state a viewer is shown, and a challenger that has led the estimate for `run` seconds."""

    state: int | None = None
    challenger: int | None = None
    run: int = 0

    def update(self, likeliest: int, hold: int, restart: bool) -> int:
        """Show the likeliest state once it has led for `hold` seconds in a row, and at once after a
        restart. A break lasts seconds, not minutes, so it is shown the moment it leads and dropped
        the moment it stops leading."""
        if self.state is None or restart or hold <= 1 or likeliest in BREAKS or self.state in BREAKS:
            self.state, self.challenger, self.run = likeliest, None, 0
        elif likeliest == self.state:
            self.challenger, self.run = None, 0
        else:
            self.run = self.run + 1 if likeliest == self.challenger else 1
            self.challenger = likeliest
            if self.run >= hold:
                self.state, self.challenger, self.run = likeliest, None, 0
        return self.state


@dataclass(frozen=True)
class Estimate:
    period: int
    second: int
    belief: np.ndarray  # chance of each state in LABELS
    shown: int  # index into LABELS of the state a viewer is shown

    @property
    def label(self) -> str:
        return LABELS[self.shown]


class StateTracker:
    """The state model run over a feed as it arrives, one message at a time.

    `observe` returns the seconds it could newly estimate: those whose look-ahead the feed has now
    passed. With `collect` set, it also keeps each second's evidence and whether a goal came just
    before it, which is what training fits on.
    """

    def __init__(
        self,
        frames: Frames,
        shape: dict[int, np.ndarray],
        model: StateModel | None,
        lag: int | None = None,
        collect: bool = False,
    ):
        if model is None and lag is None:
            raise ValueError("a lag is needed without a model")
        self.model = model
        self.lag = model.lag if model is not None else int(lag or 0)
        self.features = StateFeatures(frames, self.lag, shape)
        self.collect = collect
        self.rows: list[tuple[int, int, bool, np.ndarray]] = []  # (period, second, after a goal, evidence)
        self.belief: np.ndarray | None = None
        self.shown = Shown()
        self.latest: Estimate | None = None
        self._period: int | None = None
        self._next = 0
        self._goals: list[float] = []  # goal times this period, each restarting the estimate once
        self._score_diff = 0

    def observe(self, m: dict) -> list[Estimate]:
        kind = m["type"]
        if kind in ("match_info", "amendment"):
            return []
        period, t = int(m["period"]), float(m["t"])
        if kind == "period_start":
            self._period = period
            self._next = 0
            self._goals = []
            self.features.start_period(period, self._score_diff)
            self.belief = None
            self.shown = Shown()
            return []
        if self._period != period:
            return []
        if kind in ("period_end", "match_end"):
            out = self._finalize(int(np.floor(t)), end=t)
            self._period = None
            if isinstance(m.get("score"), dict):
                self._score_diff = int(m["score"]["home"]) - int(m["score"]["away"])
            return out
        out = self._finalize(int(np.floor(t)) - self.lag, end=None)
        self.features.add(m)
        if kind == "goal":
            self._goals.append(t)
        if isinstance(m.get("score"), dict):
            self._score_diff = int(m["score"]["home"]) - int(m["score"]["away"])
        return out

    def _finalize(self, last: int, end: float | None) -> list[Estimate]:
        """Estimate seconds up to and including `last`."""
        out: list[Estimate] = []
        while self._next <= last:
            s = self._next
            x = self.features.vector(s, end)
            restart = False
            while self._goals and self._goals[0] <= s:
                self._goals.pop(0)
                restart = True
            if self.collect:
                self.rows.append((self.features.period, s, restart, x))
            if self.model is not None:
                self.belief = self.model.step(self.belief, x, restart)
                shown = self.shown.update(int(np.argmax(self.belief)), self.model.hold, restart)
                self.latest = Estimate(self.features.period, s, self.belief, shown)
                out.append(self.latest)
            self._next += 1
        return out
