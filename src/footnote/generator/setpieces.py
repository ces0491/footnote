"""Where players stand for restarts, in each team's own frame.

Targets are assigned by role and height: tall defenders go into the box for
corners, the quickest players stay back, the goalkeeper keeps their goal.
"""

from __future__ import annotations

import numpy as np

from footnote.generator.formations import Slot
from footnote.generator.pitch import HALF_WIDTH, LENGTH, WIDTH

_ATTACK_BOX = [(99.5, 30.5), (99.0, 38.0), (95.0, 34.0), (96.5, 26.0), (96.5, 42.0), (91.0, 31.0)]
_ATTACK_EDGE = [(84.0, 27.0), (84.0, 41.0), (88.0, 34.0)]
_ATTACK_BACK = [(58.0, 24.0), (58.0, 44.0)]
_DEFEND_BOX = [
    (0.8, 30.8),
    (0.8, 37.2),
    (5.0, 29.0),
    (5.0, 34.0),
    (5.0, 39.0),
    (8.5, 27.0),
    (8.5, 34.0),
    (8.5, 41.0),
    (12.5, 31.0),
    (12.5, 37.0),
]
_DEFEND_OUT = [(30.0, 34.0)]


def corner_targets(
    slots: tuple[Slot, ...],
    active: np.ndarray,
    heights: np.ndarray,
    attacking: bool,
    taker: int | None,
    corner_v: float,
) -> np.ndarray:
    """Corner positions for one team (team frame). corner_v is the corner's lateral position."""
    n = len(slots)
    targets = np.zeros((n, 2))
    order = [i for i in np.argsort(-heights) if active[i] and slots[i].role != "GK" and i != taker]
    if attacking:
        # The two deepest-lying outfielders hold back against the counter.
        back = sorted(order, key=lambda i: slots[i].row)[:2]
        rest = [i for i in order if i not in back]
        for i, spot in zip(rest, _ATTACK_BOX + _ATTACK_EDGE, strict=False):
            targets[i] = spot
        for i, spot in zip(back, _ATTACK_BACK, strict=False):
            targets[i] = spot
        for i, slot in enumerate(slots):
            if slot.role == "GK":
                targets[i] = (8.0, HALF_WIDTH)
        if taker is not None:
            targets[taker] = (LENGTH - 0.3, 0.3 if corner_v < HALF_WIDTH else WIDTH - 0.3)
    else:
        forward = sorted(order, key=lambda i: -slots[i].row)[:1]
        rest = [i for i in order if i not in forward]
        for i, spot in zip(rest, _DEFEND_BOX, strict=False):
            targets[i] = spot
        for i, spot in zip(forward, _DEFEND_OUT, strict=False):
            targets[i] = spot
        for i, slot in enumerate(slots):
            if slot.role == "GK":
                targets[i] = (0.6, HALF_WIDTH)
    return targets


def wall_targets(
    slots: tuple[Slot, ...], active: np.ndarray, spot: np.ndarray, attacking: bool, taker: int | None, base: np.ndarray
) -> np.ndarray:
    """Free kick in or near the attacking third: defenders build a wall 9.15 m from the ball."""
    targets = base.copy()
    if attacking:
        if taker is not None:
            targets[taker] = spot - np.array([0.6, 0.0])
        return targets
    goal = np.array([0.0, HALF_WIDTH])
    to_goal = goal - spot
    d = float(np.hypot(*to_goal)) or 1.0
    centre = spot + to_goal / d * 9.15
    perp = np.array([-to_goal[1], to_goal[0]]) / d
    outfield = [i for i in range(len(slots)) if active[i] and slots[i].role != "GK"]
    nearest = sorted(outfield, key=lambda i: float(np.hypot(*(base[i] - centre))))[:4]
    for k, i in enumerate(nearest):
        targets[i] = centre + perp * (k - 1.5) * 0.6
    return targets


def penalty_targets(slots: tuple[Slot, ...], active: np.ndarray, attacking: bool, taker: int | None) -> np.ndarray:
    """Everyone except the taker and the keeper waits outside the box, behind the ball."""
    targets = np.zeros((len(slots), 2))
    arc = [
        (84.5, 22.0),
        (84.0, 27.0),
        (83.0, 31.0),
        (83.0, 37.0),
        (84.0, 41.0),
        (84.5, 46.0),
        (80.0, 30.0),
        (80.0, 38.0),
        (76.0, 34.0),
        (70.0, 34.0),
    ]
    k = 0
    for i, slot in enumerate(slots):
        if not active[i]:
            continue
        if slot.role == "GK":
            targets[i] = (6.0, HALF_WIDTH) if attacking else (0.3, HALF_WIDTH)
            continue
        if attacking and i == taker:
            targets[i] = (LENGTH - 12.5, HALF_WIDTH)
            continue
        u, v = arc[k % len(arc)]
        targets[i] = (u, v + (0.8 if attacking else -0.8)) if attacking else (LENGTH - u, WIDTH - v + 0.8)
        k += 1
    return targets


def kickoff_targets(slots: tuple[Slot, ...], active: np.ndarray, kicking: bool) -> np.ndarray:
    """Formation spread in the team's own half; the kicking side has two players on the ball."""
    targets = np.zeros((len(slots), 2))
    taker_set = False
    for i, slot in enumerate(slots):
        if not active[i]:
            continue
        if slot.role == "GK":
            targets[i] = (4.0, HALF_WIDTH)
            continue
        u = 14.0 + 35.0 * slot.row
        v = HALF_WIDTH + slot.col * 54.0
        if kicking and slot.line == "att" and not taker_set:
            targets[i] = (LENGTH / 2 - 0.3, HALF_WIDTH)
            taker_set = True
            continue
        if not kicking:
            # Defending side stays outside the centre circle.
            u = min(u, LENGTH / 2 - 10.0) if abs(v - HALF_WIDTH) < 10.0 else min(u, LENGTH / 2 - 1.0)
        targets[i] = (min(u, LENGTH / 2 - 1.0), v)
    return targets
