"""Player and ball tracking at a fixed frame rate, synthesised from simulation keyframes.

The simulation records every player's position at each action boundary. Players
move between keyframes along cubic Hermite curves (Catmull-Rom tangents, capped
at each player's speed), so paths are smooth and pass exactly through the
keyframes: positions in event freeze frames match the tracking at that instant.
The ball follows the physics of the action in each interval: a rolling pass
decelerates, a lofted ball arcs, a carried ball stays at the carrier's feet.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from footnote.generator.sim import Keyframe, MatchSim

FRAME_RATE = 10  # frames per second
MAX_SPEED = 10.4  # m/s; about 37 km/h, the top end of recorded sprint speeds


@dataclass
class Tracking:
    period: np.ndarray  # (N,) int8
    t: np.ndarray  # (N,) float32, seconds since the period started
    players: np.ndarray  # (N, 22, 2) float32 absolute positions; NaN while a slot is empty
    ball: np.ndarray  # (N, 3) float32 x, y, z
    occupancy: np.ndarray  # (N,) int16 index into slot_players
    slot_players: list[tuple[str, ...]]  # player id in each of the 22 slots, per occupancy version

    def save(self, path: str) -> None:
        """Write a compressed .npz. Positions are stored as int16 centimetres; EMPTY marks an empty slot."""
        np.savez_compressed(
            path,
            period=self.period,
            t=self.t,
            players_cm=_to_cm(self.players),
            ball_cm=_to_cm(self.ball),
            occupancy=self.occupancy,
            slot_players=np.array(self.slot_players, dtype="U16"),
            frame_rate=np.array(FRAME_RATE),
        )

    @classmethod
    def load(cls, path: str) -> Tracking:
        with np.load(path) as z:
            return cls(
                period=z["period"],
                t=z["t"],
                players=_from_cm(z["players_cm"]),
                ball=_from_cm(z["ball_cm"]),
                occupancy=z["occupancy"],
                slot_players=[tuple(str(p) for p in row) for row in z["slot_players"]],
            )


EMPTY = np.iinfo(np.int16).min


def _to_cm(a: np.ndarray) -> np.ndarray:
    out = np.round(np.nan_to_num(a, nan=np.nan) * 100.0)
    return np.where(np.isnan(out), EMPTY, np.clip(out, EMPTY + 1, np.iinfo(np.int16).max)).astype(np.int16)


def _from_cm(a: np.ndarray) -> np.ndarray:
    return np.where(a == EMPTY, np.nan, a.astype(np.float32) / 100.0).astype(np.float32)


def build_tracking(sim: MatchSim, frame_rate: int = FRAME_RATE) -> Tracking:
    periods, ts, players, balls, occ = [], [], [], [], []
    for period in (1, 2):
        kfs = [k for k in sim.keyframes if k.period == period]
        if len(kfs) < 2:
            continue
        times = np.array([k.t for k in kfs])
        frames = np.arange(0.0, times[-1], 1.0 / frame_rate)
        pos = _players_at(kfs, times, frames)
        ball = _ball_at(kfs, times, frames, pos)
        idx = np.clip(np.searchsorted(times, frames, side="right") - 1, 0, len(kfs) - 1)
        # A slot is on the pitch through an interval only if it is at both ends: a player sent off
        # leaves at the last keyframe he was on, rather than gliding to wherever the simulation parks him.
        act = np.stack([k.active for k in kfs])
        nxt = np.minimum(idx + 1, len(kfs) - 1)
        active = act[idx] & act[nxt]
        pos[~active] = np.nan
        periods.append(np.full(len(frames), period, dtype=np.int8))
        ts.append(frames.astype(np.float32))
        players.append(pos.astype(np.float32))
        balls.append(ball.astype(np.float32))
        occ.append(np.array([kfs[i].occupancy for i in idx], dtype=np.int16))
    return Tracking(
        period=np.concatenate(periods),
        t=np.concatenate(ts),
        players=np.concatenate(players),
        ball=np.concatenate(balls),
        occupancy=np.concatenate(occ),
        slot_players=list(sim.occupancy),
    )


def _players_at(kfs: list[Keyframe], times: np.ndarray, frames: np.ndarray) -> np.ndarray:
    """Cubic Hermite interpolation of all 22 slots through the keyframes."""
    P = np.stack([k.pos for k in kfs])  # (K, 22, 2)
    K = len(kfs)
    # Catmull-Rom tangents from neighbouring keyframes, one-sided at the ends.
    m = np.zeros_like(P)
    m[1:-1] = (P[2:] - P[:-2]) / np.maximum(times[2:] - times[:-2], 1e-3)[:, None, None]
    m[0] = (P[1] - P[0]) / max(times[1] - times[0], 1e-3)
    m[-1] = (P[-1] - P[-2]) / max(times[-1] - times[-2], 1e-3)
    # No tangent faster than the quickest player can run keeps curves from overshooting.
    speed = np.linalg.norm(m, axis=2, keepdims=True)
    m = np.where(speed > 10.5, m * (10.5 / np.maximum(speed, 1e-9)), m)
    idx = np.clip(np.searchsorted(times, frames, side="right") - 1, 0, K - 2)
    t0, t1 = times[idx], times[idx + 1]
    h = np.maximum(t1 - t0, 1e-6)
    s = np.clip((frames - t0) / h, 0.0, 1.0)[:, None, None]
    h = h[:, None, None]
    h00 = 2 * s**3 - 3 * s**2 + 1
    h10 = s**3 - 2 * s**2 + s
    h01 = -2 * s**3 + 3 * s**2
    h11 = s**3 - s**2
    out = h00 * P[idx] + h10 * h * m[idx] + h01 * P[idx + 1] + h11 * h * m[idx + 1]
    # Where the curve would run faster than a person can, fall back to a straight line between
    # the two keyframes for that player and interval.
    linear = (1 - s) * P[idx] + s * P[idx + 1]
    step = np.zeros(len(frames), dtype=bool)
    step[1:] = idx[1:] == idx[:-1]
    speed = np.zeros(out.shape[:2])
    speed[1:] = np.linalg.norm(np.diff(out, axis=0), axis=2) / np.maximum(np.diff(frames), 1e-6)[:, None]
    speed[~step] = 0.0
    too_fast = np.zeros((K, out.shape[1]), dtype=bool)
    np.logical_or.at(too_fast, idx, speed > MAX_SPEED)
    mask = too_fast[idx]
    out[mask] = linear[mask]
    return out


def _ball_at(kfs: list[Keyframe], times: np.ndarray, frames: np.ndarray, players: np.ndarray) -> np.ndarray:
    out = np.zeros((len(frames), 3))
    idx = np.clip(np.searchsorted(times, frames, side="right") - 1, 0, len(kfs) - 2)
    for k in range(len(kfs) - 1):
        sel = np.where(idx == k)[0]
        if len(sel) == 0:
            continue
        t0, t1 = times[k], times[k + 1]
        dur = max(t1 - t0, 1e-6)
        s = np.clip((frames[sel] - t0) / dur, 0.0, 1.0)
        start = kfs[k].ball[:2]
        path = kfs[k + 1].ball_path
        kind = path[0]
        if kind == "carry":
            carrier = int(path[1])
            feet = players[sel, carrier, :]
            # The ball runs just ahead of the carrier in the direction of travel.
            direction = np.gradient(feet, axis=0) if len(sel) > 1 else np.zeros_like(feet)
            norm = np.maximum(np.linalg.norm(direction, axis=1, keepdims=True), 1e-6)
            out[sel, :2] = feet + direction / norm * 0.6 * (norm > 1e-3)
            out[sel, 2] = 0.0
        elif kind == "pass":
            a, b, v0, lofted = np.asarray(path[1]), np.asarray(path[2]), float(path[3]), bool(path[4])
            dist = float(np.hypot(*(b - a)))
            if lofted:
                frac = s
                peak = float(np.clip(dist / 6.0, 1.5, 14.0))
                out[sel, 2] = 4 * peak * s * (1 - s)
            else:
                # Uniform deceleration from v0 that covers the distance in the interval.
                if v0 * dur > dist > 0:
                    decel = 2 * (v0 * dur - dist) / dur**2
                    tau = s * dur
                    frac = np.clip((v0 * tau - 0.5 * decel * tau**2) / dist, 0.0, 1.0)
                else:
                    frac = s
                out[sel, 2] = 0.0
            out[sel, :2] = a + frac[:, None] * (b - a)
        elif kind == "shot":
            a, b, z_end = np.asarray(path[1]), np.asarray(path[2]), float(path[4])
            out[sel, :2] = a + s[:, None] * (b - a)
            out[sel, 2] = 0.2 + s * (z_end - 0.2)
        elif kind == "roll":
            b = np.asarray(path[1])
            out[sel, :2] = start + s[:, None] * (b - start)
            out[sel, 2] = 0.0
        else:  # dead ball: carried or rolled to the restart spot early in the stoppage
            b = np.asarray(path[1])
            move = np.clip(s * 4.0, 0.0, 1.0)[:, None]
            out[sel, :2] = start + move * (b - start)
            out[sel, 2] = 0.0
    return out
