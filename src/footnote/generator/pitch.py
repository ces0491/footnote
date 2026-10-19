"""Pitch geometry and coordinate frames.

Absolute frame: x runs along the pitch from 0 to 105 m, y across it from 0 to
68 m, origin at a corner. Every position written to the feed is absolute.

Team frame: u is progress towards the opponent's goal (0 at the team's own goal
line, 105 at the opponent's), v is lateral and increases towards the team's
left. A team attacking towards x = 105 has (u, v) = (x, y); a team attacking
towards x = 0 has (u, v) = (105 - x, 68 - y). The map is a half-turn, so it is
its own inverse and keeps left and right where they are.
"""

from __future__ import annotations

import numpy as np

LENGTH = 105.0
WIDTH = 68.0
HALF_WIDTH = WIDTH / 2
GOAL_WIDTH = 7.32
GOAL_HEIGHT = 2.44
BOX_DEPTH = 16.5
BOX_HALF_WIDTH = 20.16
SIX_DEPTH = 5.5
SIX_HALF_WIDTH = 9.16
PENALTY_SPOT = 11.0
CENTRE_CIRCLE_RADIUS = 9.15

# Angle the goal mouth subtends from the penalty spot, used to normalise angles.
SPOT_GOAL_ANGLE = 2.0 * float(np.arctan((GOAL_WIDTH / 2) / PENALTY_SPOT))


def to_frame(xy: np.ndarray, direction: int) -> np.ndarray:
    """Convert between the absolute frame and a team frame (the map is an involution)."""
    if direction == 1:
        return np.array(xy, dtype=float, copy=True)
    out = np.array(xy, dtype=float, copy=True)
    out[..., 0] = LENGTH - out[..., 0]
    out[..., 1] = WIDTH - out[..., 1]
    return out


def dist_to_goal(u: np.ndarray | float, v: np.ndarray | float) -> np.ndarray:
    """Distance from team-frame points to the centre of the opponent's goal."""
    return np.hypot(LENGTH - np.asarray(u, dtype=float), HALF_WIDTH - np.asarray(v, dtype=float))


def goal_angle(u: np.ndarray | float, v: np.ndarray | float) -> np.ndarray:
    """Angle in radians that the opponent's goal mouth subtends from team-frame points."""
    u = np.asarray(u, dtype=float)
    v = np.asarray(v, dtype=float)
    dx = np.maximum(LENGTH - u, 1e-6)
    a1 = np.arctan2(HALF_WIDTH + GOAL_WIDTH / 2 - v, dx)
    a2 = np.arctan2(HALF_WIDTH - GOAL_WIDTH / 2 - v, dx)
    return np.abs(a1 - a2)


def in_attacking_box(u: np.ndarray | float, v: np.ndarray | float) -> np.ndarray:
    return (np.asarray(u) >= LENGTH - BOX_DEPTH) & (np.abs(np.asarray(v) - HALF_WIDTH) <= BOX_HALF_WIDTH)


def in_own_box(u: np.ndarray | float, v: np.ndarray | float) -> np.ndarray:
    return (np.asarray(u) <= BOX_DEPTH) & (np.abs(np.asarray(v) - HALF_WIDTH) <= BOX_HALF_WIDTH)


def exit_point(start: np.ndarray, end: np.ndarray) -> tuple[np.ndarray, str] | None:
    """Where a straight ball path from start to end first leaves the pitch.

    Returns (point, line) with line one of "touch" or "goal", or None if the
    path stays on the pitch. Positions are absolute.
    """
    d = end - start
    best_s = 2.0
    line = ""
    for axis, limit, name in ((0, 0.0, "goal"), (0, LENGTH, "goal"), (1, 0.0, "touch"), (1, WIDTH, "touch")):
        if abs(d[axis]) < 1e-9:
            continue
        s = (limit - start[axis]) / d[axis]
        if 0.0 < s <= 1.0 and s < best_s:
            best_s = s
            line = name
    if best_s > 1.0:
        return None
    return start + best_s * d, line
