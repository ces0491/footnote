"""Each side's shape from the tracking, second by second.

For every second of play and each side, in that side's frame: how high its outfield block stands,
where its back and front lines are, how wide it spreads, how fast its players are moving, where
the ball is, and how far the ball is beyond the back line. A pressing side squeezes up towards the
ball and narrows; a side in settled possession moves the ball at walking pace; a break is a sprint.

Each second's figures are averages over the tracking frames inside it, so the state model reads a
second's shape only once its look-ahead has passed that second.
"""

from __future__ import annotations

import numpy as np

from footnote.interpret.frames import LENGTH, WIDTH, Frames
from footnote.interpret.physical import FRAME_RATE, Tracking

SHAPE_SIDE = ("block", "back_line", "front_line", "width", "speed", "ball", "ball_gap")
SHAPE_GLOBAL = ("ball_speed",)
COLUMNS = 2 * len(SHAPE_SIDE) + len(SHAPE_GLOBAL)
_OUTFIELD = (np.arange(1, 11), np.arange(12, 22))  # slot 0 and slot 11 are the goalkeepers
# What a second with no usable frame at all starts from: a mid block at walking pace.
_NEUTRAL = np.array([0.4, 0.25, 0.6, 0.2, 1.5, 0.5, 0.25] * 2 + [5.0])


def _mean(a: np.ndarray) -> np.ndarray:
    """Row means over the finite entries; NaN for a row with none."""
    ok = np.isfinite(a)
    count = ok.sum(axis=1)
    total = np.where(ok, a, 0.0).sum(axis=1)
    return np.where(count > 0, total / np.maximum(count, 1), np.nan)


def per_second(tracking: Tracking, frames: Frames) -> dict[int, np.ndarray]:
    """Period -> (seconds, COLUMNS): each second's shape figures, in SHAPE_SIDE order per side, then
    SHAPE_GLOBAL."""
    out: dict[int, np.ndarray] = {}
    for period in sorted({int(p) for p in np.unique(tracking.period)}):
        sel = np.flatnonzero(tracking.period == period)
        players = tracking.players[sel].astype(np.float64)
        ball = tracking.ball[sel, :2].astype(np.float64)
        occupancy = tracking.occupancy[sel]
        moved = np.full(players.shape[:2], np.nan)
        same = occupancy[1:] == occupancy[:-1]
        step = np.linalg.norm(np.diff(players, axis=0), axis=2) * FRAME_RATE
        step[~same] = np.nan
        moved[1:] = step
        ball_speed = np.zeros(len(sel))
        ball_speed[1:] = np.linalg.norm(np.diff(ball, axis=0), axis=1) * FRAME_RATE
        cols = []
        for side in (0, 1):
            xy = frames.to_frame(side, period, players[:, _OUTFIELD[side], :])
            u, v = xy[..., 0], xy[..., 1]
            on = ~np.isnan(u)
            count = on.sum(axis=1)
            ordered = np.sort(np.where(on, u, np.inf), axis=1)
            back = ordered[:, 1]
            front = np.take_along_axis(ordered, np.maximum(count - 2, 0)[:, None], axis=1)[:, 0]
            ball_u = frames.to_frame(side, period, ball)[:, 0]
            cols += [
                _mean(u) / LENGTH,
                back / LENGTH,
                front / LENGTH,
                np.sqrt(np.maximum(_mean(v**2) - _mean(v) ** 2, 0.0)) / WIDTH,
                _mean(moved[:, _OUTFIELD[side]]),
                ball_u / LENGTH,
                (ball_u - back) / LENGTH,
            ]
        cols.append(np.minimum(ball_speed, 40.0))
        values = np.stack(cols, axis=1)
        seconds = np.floor(tracking.t[sel] + 1e-6).astype(np.int64)
        n = int(seconds.max()) + 1
        sums = np.zeros((n, COLUMNS))
        counts = np.zeros((n, COLUMNS))
        ok = np.isfinite(values)
        np.add.at(sums, seconds, np.where(ok, values, 0.0))
        np.add.at(counts, seconds, ok)
        means = np.where(counts > 0, sums / np.maximum(counts, 1), np.nan)
        # A second with no usable frame repeats the one before it.
        for i in range(n):
            bad = ~np.isfinite(means[i])
            if bad.any():
                means[i, bad] = means[i - 1, bad] if i else _NEUTRAL[bad]
        out[period] = means
    return out
