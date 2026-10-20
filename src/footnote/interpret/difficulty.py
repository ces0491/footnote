"""How hard a pass was: the chance it reaches its target, and difficulty as one minus that chance.

The inputs are what an event feed and a tracking feed give at the moment the ball is played: where
the pass starts, its length, height and type (cross, through ball, set piece, header), whether the
passer was under pressure, and where every player stands. Nothing about the passer or the club is
used, so a rating says how hard the pass was, not who tried it.

The target is the point the pass's length away from the passer, towards where the intended receiver
stood as the ball was played. The feed's end point would give the outcome away: a pass that was cut
out ends where it was cut out, and one that ran out of play ends off line. A cross is taken to aim
at a point in front of goal, since a cross names its receiver only when it reaches one.

The model is a logistic regression over these inputs, fitted by `python -m footnote.interpret` on
generated matches and scored against each pass's true probability in the answer key
(docs/models.md). Its parameters are in `params/difficulty.json`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from footnote.interpret.frames import HALF_WIDTH, LENGTH, Frames, in_box
from footnote.interpret.physical import Positions

PARAMS = Path(__file__).with_name("params") / "difficulty.json"

CROSS_TARGET = (97.0, HALF_WIDTH)  # in the crossing side's frame
DEFENDER_SPEED = 7.0  # m/s an opponent can close at, for the interception margin
REACTION = 0.25  # seconds before an opponent reacts to the pass
SET_PIECES = ("free_kick", "corner", "goal_kick", "throw_in", "kick_off")

FEATURES = (
    "length",
    "length_over_25",
    "lofted",
    "lofted_length",
    "header",
    "cross",
    "through_ball",
    *SET_PIECES,
    "under_pressure",
    "start_u",
    "start_wide",
    "target_u",
    "target_wide",
    "progress",
    "into_box",
    "flight",
    # From the tracking at the moment of the pass:
    "passer_space",
    "passer_tight",
    "target_space",
    "target_tight",
    "target_crowd",
    "mate_to_target",
    "lane_gap",
    "lane_crowd",
    "intercept_margin",
    "intercept_threat",
    "cover_behind",
    "cross_crowd",
)


@dataclass(frozen=True)
class PassGeometry:
    side: int
    start: np.ndarray  # (2,) in the passing side's frame
    target: np.ndarray  # (2,)
    length: float
    speed: float  # m/s off the foot


def geometry(m: dict, frames: Frames, positions: Positions) -> PassGeometry | None:
    side = frames.side(m.get("team_id"))
    if side is None:
        return None
    period = int(m["period"])
    start_abs = np.array([m["x"], m["y"]], dtype=float)
    length = float(m["length"])
    start = frames.to_frame(side, period, start_abs)
    if m.get("cross"):
        target = np.array(CROSS_TARGET)
    else:
        towards = _receiver(m, positions)
        if towards is None:
            # Nobody to aim at in the tracking: fall back on the direction the ball went.
            towards = np.array([m["end_x"], m["end_y"]], dtype=float)
        heading = towards - start_abs
        norm = float(np.hypot(*heading))
        target_abs = start_abs + heading / norm * length if norm > 0.5 else towards
        target = frames.to_frame(side, period, target_abs)
    speed = max(float(m.get("speed_kmh") or 0.0) / 3.6, 1.0)
    return PassGeometry(side, start, target, length, speed)


def _receiver(m: dict, positions: Positions) -> np.ndarray | None:
    pid = m.get("recipient_id")
    if pid not in positions.player_ids:
        return None
    at = positions.players[positions.player_ids.index(pid)]
    return None if np.isnan(at).any() else np.asarray(at, dtype=float)


def features(m: dict, frames: Frames, positions: Positions | None) -> np.ndarray | None:
    """The model's inputs for one pass message, in FEATURES order; None if it isn't a side's pass or
    the tracking has no frame for its moment."""
    if positions is None:
        return None
    g = geometry(m, frames, positions)
    if g is None:
        return None
    lofted = m["height"] == "high"
    pass_type = m["pass_type"]
    start_u, start_v = float(g.start[0]), float(g.start[1])
    target_u, target_v = float(g.target[0]), float(g.target[1])
    flight = g.length / (0.8 * g.speed)
    base = [
        g.length,
        max(g.length - 25.0, 0.0),
        float(lofted),
        g.length * lofted,
        float(m["body_part"] == "head"),
        float(bool(m.get("cross"))),
        float(bool(m.get("through_ball"))),
        *(float(pass_type == kind) for kind in SET_PIECES),
        float(bool(m.get("under_pressure"))),
        start_u / LENGTH,
        abs(start_v - HALF_WIDTH) / HALF_WIDTH,
        target_u / LENGTH,
        abs(target_v - HALF_WIDTH) / HALF_WIDTH,
        (target_u - start_u) / 10.0,
        float(in_box(target_u, target_v) and not in_box(start_u, start_v)),
        flight,
    ]
    return np.array(base + _space(g, lofted, flight, bool(m.get("cross")), m, frames, positions))


def _space(
    g: PassGeometry,
    lofted: bool,
    flight: float,
    cross: bool,
    m: dict,
    frames: Frames,
    positions: Positions,
) -> list[float]:
    period = int(m["period"])
    allp = frames.to_frame(g.side, period, positions.players)
    on = ~np.isnan(allp[:, 0])
    own = np.zeros(len(allp), dtype=bool)
    own[: len(allp) // 2] = g.side == 0
    own[len(allp) // 2 :] = g.side == 1
    opps = allp[on & ~own]
    passer = positions.player_ids.index(m["player_id"]) if m["player_id"] in positions.player_ids else -1
    mates_mask = on & own
    if passer >= 0:
        mates_mask[passer] = False
    mates = allp[mates_mask]

    passer_space = _nearest(opps, g.start, cap=10.0)
    target_space = _nearest(opps, g.target, cap=15.0)
    target_crowd = float(np.sum(np.linalg.norm(opps - g.target, axis=1) < 5.0)) if len(opps) else 0.0
    mate_to_target = _nearest(mates, g.target, cap=20.0)

    # Opponents along the line of the pass: how close they stand to it, and how much time they'd
    # have in hand to get there before the ball. A lofted ball can be cut out only near either end.
    ab = g.target - g.start
    length2 = max(float(ab @ ab), 1e-6)
    rel = opps - g.start
    s = np.clip(rel @ ab / length2, 0.0, 1.0) if len(opps) else np.zeros(0)
    closest = g.start + s[:, None] * ab
    d = np.linalg.norm(opps - closest, axis=1) if len(opps) else np.zeros(0)
    live = (s > 0.05) & (~lofted | (s < 0.15) | (s > 0.85))
    t_ball = s * np.sqrt(length2) / (0.8 * g.speed)
    t_def = np.maximum(d - 1.0, 0.0) / DEFENDER_SPEED + REACTION
    margin = t_def - t_ball
    lane_gap = float(min(d[live].min(), 10.0)) if live.any() else 10.0
    lane_crowd = float(np.sum(live & (d < 2.0)))
    intercept_margin = float(np.clip(margin[live].min(), -2.0, 3.0)) if live.any() else 3.0
    # Defenders goal-side of the target: cover the receiver has to beat.
    cover_behind = float(np.sum(opps[:, 0] > g.target[0])) if len(opps) else 0.0
    cross_crowd = float(np.sum(np.linalg.norm(opps - g.target, axis=1) < 10.0)) if cross and len(opps) else 0.0
    return [
        passer_space,
        float(np.exp(-passer_space / 2.5)),
        target_space,
        float(np.exp(-max(target_space - DEFENDER_SPEED * 0.55 * flight, 0.0) / 2.0)),
        target_crowd,
        mate_to_target,
        lane_gap,
        lane_crowd,
        intercept_margin,
        float(np.exp(-max(intercept_margin, 0.0) / 0.3)),
        cover_behind / 10.0,
        cross_crowd,
    ]


def _nearest(points: np.ndarray, at: np.ndarray, cap: float) -> float:
    if len(points) == 0:
        return cap
    return float(min(np.linalg.norm(points - at, axis=1).min(), cap))


@dataclass(frozen=True)
class DifficultyModel:
    mean: np.ndarray
    scale: np.ndarray
    coef: np.ndarray
    intercept: float

    @classmethod
    def load(cls, path: Path = PARAMS) -> DifficultyModel:
        params = json.loads(path.read_text(encoding="utf-8"))
        if tuple(params["features"]) != FEATURES:
            raise ValueError(f"{path}: fitted on different features; refit with python -m footnote.interpret")
        return cls(
            mean=np.array(params["mean"]),
            scale=np.array(params["scale"]),
            coef=np.array(params["coef"]),
            intercept=float(params["intercept"]),
        )

    def completion(self, x: np.ndarray) -> np.ndarray:
        """Chance each pass (rows of x) reaches its target."""
        z = ((np.atleast_2d(x) - self.mean) / self.scale) @ self.coef + self.intercept
        return 1.0 / (1.0 + np.exp(-z))
