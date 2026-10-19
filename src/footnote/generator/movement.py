"""Team shape and player movement.

Each team keeps its formation inside a block whose position, length and width
depend on where the ball is, who has it, the team's style and the current
regime. Defenders are pulled towards nearby attackers; forwards play on the
shoulder of the last defender, with some error in the timing of their runs,
which is where offsides come from. Players then move towards their targets with
limited speed and acceleration.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from footnote.generator.formations import Slot
from footnote.generator.pitch import HALF_WIDTH, LENGTH, WIDTH
from footnote.generator.regimes import Intent


def offside_line(opponents_u: np.ndarray, ball_u: float) -> float:
    """Team-frame u of the offside line set by the opponents (second-last opponent or the ball).

    opponents_u are the opponents' positions in the attacking team's frame. The line is
    never behind halfway: a player in their own half can't be offside.
    """
    if len(opponents_u) < 2:
        return LENGTH
    second_last = float(np.partition(opponents_u, -2)[-2])
    return max(second_last, ball_u, LENGTH / 2)


@lru_cache(maxsize=32)
def _slot_arrays(slots: tuple[Slot, ...]) -> tuple[np.ndarray, ...]:
    row = np.array([s.row for s in slots])
    col = np.array([s.col for s in slots])
    is_gk = np.array([s.role == "GK" for s in slots])
    is_fb = np.array([s.role in ("RB", "LB") for s in slots])
    is_att = np.array([s.line == "att" for s in slots])
    is_mid = np.array([s.line == "mid" for s in slots])
    is_striker = np.array([s.role == "ST" for s in slots])
    is_wide_fwd = np.array([s.role in ("RW", "LW") for s in slots])
    is_am = np.array([s.role == "AM" for s in slots])
    return row, col, is_gk, is_fb, is_att, is_mid, is_striker, is_wide_fwd, is_am


def shape_targets(
    slots: tuple[Slot, ...],
    active: np.ndarray,
    ball: np.ndarray,
    in_possession: bool,
    intent: Intent,
    style: dict[str, float],
    own_pos: np.ndarray,
    opp_pos: np.ndarray,
    run_offsets: np.ndarray,
    jitter: np.ndarray,
) -> np.ndarray:
    """Target positions for one team's eleven, in that team's frame.

    ball, own_pos and opp_pos are in the team's frame. run_offsets is each player's
    current run-timing error relative to the offside line (metres, positive means
    beyond it). jitter is a slowly varying personal offset.
    """
    bu, bv = float(ball[0]), float(ball[1])
    row, col, is_gk, is_fb, is_att, is_mid, is_striker, is_wide_fwd, is_am = _slot_arrays(slots)
    row = row.copy()
    if in_possession:
        line = float(np.clip(bu - (26.0 + 8.0 * style["directness"]), 10.0, 36.0 + 22.0 * style["line"]))
        line = float(np.clip(line + 0.45 * intent.territory, 8.0, 62.0))
        length = 34.0 + 10.0 * style["directness"]
        width = 46.0 + 18.0 * style["width"]
        shift = 0.30 * (bv - HALF_WIDTH)
        row = row + is_fb * (0.15 + 0.35 * style["width"])
        # Whatever the base shape, wide forwards and the number ten push up in possession.
        row = np.where(is_wide_fwd, np.maximum(row, 0.9), row)
        row = np.where(is_am, np.maximum(row, 0.8), row)
    else:
        top = 30.0 + 18.0 * style["line"] + 0.5 * intent.territory
        line = float(np.clip(bu - (28.0 - 8.0 * intent.press), 9.0, max(top, 10.0)))
        # The back line stays goal-side of the ball unless the ball is already behind it.
        line = min(line, max(bu - 3.0, 6.0))
        length = 22.0 + 8.0 * (1.0 - style["press"])
        width = 30.0 + 10.0 * (1.0 - intent.press)
        shift = 0.50 * (bv - HALF_WIDTH)
        # Forwards stay a little higher than the block to offer an outlet.
        row = row + is_att * 0.15

    u = line + row * length
    v = HALF_WIDTH + shift + col * width
    if in_possession and len(opp_pos):
        o_line = offside_line(opp_pos[:, 0], bu)
        if bu < o_line:
            # Strikers play on the last defender's shoulder; wingers and midfielders don't run
            # beyond the line until the ball is played.
            shoulder = o_line - 3.0 + 1.5 * style["directness"]
            u = np.where(is_striker, np.maximum(u, shoulder), u)
            u = np.where(is_wide_fwd, np.maximum(u, shoulder - 5.0), u)
            limit = o_line + run_offsets
            u = np.where((is_att | is_mid | is_wide_fwd | is_am) & (u > limit), limit, u)
    targets = np.stack([u, v], axis=1)
    keeper = _keeper_target(bu, bv, in_possession, style)
    targets[is_gk] = keeper
    if not in_possession and len(opp_pos):
        targets = _apply_marking(targets, is_gk, active, opp_pos, ball)
    targets[~active] = own_pos[~active]
    targets[:, 0] = np.clip(targets[:, 0] + jitter[:, 0] * ~is_gk, 0.5, LENGTH - 0.5)
    targets[:, 1] = np.clip(targets[:, 1] + jitter[:, 1] * ~is_gk, 0.8, WIDTH - 0.8)
    return targets


def _keeper_target(bu: float, bv: float, in_possession: bool, style: dict[str, float]) -> np.ndarray:
    if in_possession:
        u = 5.0 + min(0.14 * bu, 6.0 + 10.0 * style["line"])
        return np.array([u, HALF_WIDTH + 0.1 * (bv - HALF_WIDTH)])
    d = float(np.hypot(bu, bv - HALF_WIDTH))
    if d < 1e-6:
        return np.array([1.2, HALF_WIDTH])
    stand = float(np.clip(1.2 + 0.09 * d, 1.2, 6.0 + 8.0 * style["line"]))
    direction = np.array([bu, bv - HALF_WIDTH]) / d
    return np.array([0.0, HALF_WIDTH]) + direction * min(stand, d)


def _apply_marking(
    targets: np.ndarray, is_gk: np.ndarray, active: np.ndarray, opp_pos: np.ndarray, ball: np.ndarray
) -> np.ndarray:
    """Pull each outfield defender towards the nearest attacker in their zone, staying goal-side."""
    dist = np.linalg.norm(targets[:, None, :] - opp_pos[None, :, :], axis=2)
    nearest = np.argmin(dist, axis=1)
    dmin = dist[np.arange(len(targets)), nearest]
    attacker = opp_pos[nearest]
    to_goal = np.array([0.0, HALF_WIDTH]) - attacker
    norm = np.maximum(np.linalg.norm(to_goal, axis=1), 1e-6)
    goal_side = attacker + to_goal / norm[:, None] * 1.8
    ball_dist = np.linalg.norm(attacker - ball, axis=1)
    weight = np.where(ball_dist < 25.0, 0.55, 0.35)
    apply = active & ~is_gk & (dmin <= 13.0)
    out = targets.copy()
    out[apply] = (1 - weight[apply, None]) * targets[apply] + weight[apply, None] * goal_side[apply]
    return out


def move(
    pos: np.ndarray,
    vel: np.ndarray,
    targets: np.ndarray,
    dt: float,
    vmax: np.ndarray,
    accel: np.ndarray,
    arrive: float | np.ndarray = 1.2,
) -> tuple[np.ndarray, np.ndarray]:
    """Advance players towards targets over dt seconds with speed and acceleration limits.

    Positions and velocities are absolute. Desired velocity heads for the target and
    eases off as it gets close; acceleration is capped per player. arrive is the time,
    per player or for all, over which a player aims to close the gap to their target.
    """
    arrive_s = np.broadcast_to(np.asarray(arrive, dtype=float), (len(pos),))
    if dt <= 0:
        return pos.copy(), vel.copy()
    new_pos = pos.copy()
    new_vel = vel.copy()
    remaining = dt
    # Sub-steps keep the integration stable for long actions.
    while remaining > 1e-9:
        h = min(remaining, 0.5)
        desired = (targets - new_pos) / np.maximum(arrive_s, h)[:, None]
        speed = np.linalg.norm(desired, axis=1)
        desired *= np.where(speed > vmax, vmax / np.maximum(speed, 1e-9), 1.0)[:, None]
        dv = desired - new_vel
        dv_norm = np.linalg.norm(dv, axis=1)
        cap = accel * h
        dv *= np.where(dv_norm > cap, cap / np.maximum(dv_norm, 1e-9), 1.0)[:, None]
        v_next = new_vel + dv
        new_pos = new_pos + 0.5 * (new_vel + v_next) * h
        new_vel = v_next
        remaining -= h
    new_pos[:, 0] = np.clip(new_pos[:, 0], -1.5, LENGTH + 1.5)
    new_pos[:, 1] = np.clip(new_pos[:, 1], -1.5, WIDTH + 1.5)
    return new_pos, new_vel
