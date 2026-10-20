"""Positions, distance covered and top speed from the tracking, and the moments worth a tag.

The tracking file (`data/matches/<id>/tracking.npz`, format in docs/data.md) stands in for a
tracking feed arriving alongside the event feed. The processor looks it up against each event's
clock, so a run sees positions, distances and speeds only up to the moment its feed has reached.

Speeds are averaged over one second, the way tracking providers report top speeds. Tags mark a
sprint above `SPRINT_KMH`, reported with its peak once the player slows below the threshold again,
and a player passing `DISTANCE_KM` covered.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

FRAME_RATE = 10  # the file records it too; checked on load
EMPTY_CM = np.iinfo(np.int16).min
SLOTS = 22  # 0-10 home, 11-21 away
SPRINT_KMH = 32.0
DISTANCE_KM = 10.0


@dataclass(frozen=True)
class Positions:
    """Everyone on the pitch at one instant, absolute metres."""

    players: np.ndarray  # (22, 2); NaN for an empty slot
    player_ids: tuple[str, ...]  # who is in each slot
    ball: np.ndarray  # (3,) x, y, z


@dataclass(frozen=True)
class Tag:
    kind: str  # "sprint" or "distance"
    player_id: str
    side: int  # 0 home, 1 away
    value: float  # km/h for a sprint, km for distance
    period: int
    t: float  # when the tag fell due: the end of the sprint, or the moment the distance was passed
    record: bool = False  # a sprint faster than any before it in the match

    @property
    def unit(self) -> str:
        return "km/h" if self.kind == "sprint" else "km"


class Tracking:
    def __init__(
        self,
        period: np.ndarray,
        t: np.ndarray,
        players: np.ndarray,
        ball: np.ndarray,
        occupancy: np.ndarray,
        slot_players: list[tuple[str, ...]],
    ) -> None:
        self.period = period.astype(np.int8)
        self.t = t.astype(np.float64)
        self.players = players
        self.ball = ball
        self.occupancy = occupancy.astype(np.int64)
        self.slot_players = slot_players
        # Frame ranges of each period, for lookups by (period, t).
        self._starts = {int(p): int(np.argmax(self.period == p)) for p in np.unique(self.period)}
        self._ends = {p: start + int(np.sum(self.period == p)) for p, start in self._starts.items()}

    @classmethod
    def load(cls, path: Path) -> Tracking:
        with np.load(path) as z:
            if int(z["frame_rate"]) != FRAME_RATE:
                raise ValueError(f"{path}: expected {FRAME_RATE} frames a second, got {int(z['frame_rate'])}")
            return cls(
                period=z["period"],
                t=z["t"],
                players=_metres(z["players_cm"]),
                ball=_metres(z["ball_cm"]),
                occupancy=z["occupancy"],
                slot_players=[tuple(str(p) for p in row) for row in z["slot_players"]],
            )

    def __len__(self) -> int:
        return len(self.t)

    def frame(self, period: int, t: float) -> int | None:
        """The last frame at or before `t` seconds into `period`; None outside the recorded periods."""
        if period not in self._starts:
            return None
        start, end = self._starts[period], self._ends[period]
        i = start + int(np.searchsorted(self.t[start:end], t + 1e-6, side="right")) - 1
        return i if i >= start else None

    def positions(self, period: int, t: float) -> Positions | None:
        f = self.frame(period, t)
        if f is None:
            return None
        return Positions(self.players[f], self.slot_players[int(self.occupancy[f])], self.ball[f])


def _metres(cm: np.ndarray) -> np.ndarray:
    return np.where(cm == EMPTY_CM, np.nan, cm.astype(np.float32) / 100.0).astype(np.float32)


class Physical:
    """Every player's distance and top speed through the match, and the tags, from the tracking."""

    def __init__(self, tracking: Tracking, home_id: str, away_id: str) -> None:
        self.tracking = tracking
        n = len(tracking)
        self.player_ids = sorted({pid for row in tracking.slot_players for pid in row})
        index = {pid: i for i, pid in enumerate(self.player_ids)}
        self.side = np.array([0 if pid.startswith(f"{home_id}-") else 1 for pid in self.player_ids])
        if not all(pid.startswith((f"{home_id}-", f"{away_id}-")) for pid in self.player_ids):
            raise ValueError("tracking names players of neither club")
        owner = np.array([[index[pid] for pid in row] for row in tracking.slot_players])[tracking.occupancy]

        # Distance run from the previous frame; nothing across a period break or a substitution.
        same = np.zeros(n, dtype=bool)
        same[1:] = (tracking.period[1:] == tracking.period[:-1]) & (tracking.occupancy[1:] == tracking.occupancy[:-1])
        step = np.zeros((n, SLOTS))
        step[1:] = np.linalg.norm(np.diff(tracking.players.astype(np.float64), axis=0), axis=2)
        step[~same] = 0.0
        step = np.nan_to_num(step, nan=0.0)

        # Speed over the trailing second, within a stretch with the same players on.
        segment_start = np.maximum.accumulate(np.where(~same, np.arange(n), 0))
        cum = np.concatenate([np.zeros((1, SLOTS)), np.cumsum(step, axis=0)])
        frames = np.arange(n)
        back = np.maximum(frames + 1 - FRAME_RATE, segment_start)
        ran = cum[frames + 1] - cum[back]
        full = (frames + 1 - back) >= FRAME_RATE
        speed = np.where(full[:, None], ran, 0.0) * 3.6  # metres over one second, in km/h

        rows = np.repeat(frames, SLOTS)
        per_frame = np.zeros((n, len(self.player_ids)))
        np.add.at(per_frame, (rows, owner.ravel()), step.ravel())
        self.distance_m = np.cumsum(per_frame, axis=0)
        fastest = np.zeros((n, len(self.player_ids)))
        np.maximum.at(fastest, (rows, owner.ravel()), speed.ravel())
        self.top_kmh = np.maximum.accumulate(fastest, axis=0)
        self.tags = self._tags(fastest)
        self._tag_frames = np.array([tracking.frame(tag.period, tag.t) for tag in self.tags], dtype=np.int64)

    def _tags(self, speed: np.ndarray) -> list[Tag]:
        tr = self.tracking
        found: list[tuple[int, Tag]] = []
        above = speed > SPRINT_KMH
        for p, pid in enumerate(self.player_ids):
            col = above[:, p]
            # A sprint ends on the first frame back under the threshold; its peak is reported then.
            starts = np.flatnonzero(col & ~np.concatenate([[False], col[:-1]]))
            ends = np.flatnonzero(~col & np.concatenate([[False], col[:-1]]))
            for start in starts:
                later = ends[ends > start]
                if len(later) == 0:
                    continue  # still sprinting when the recording stops
                end = int(later[0])
                peak = float(speed[start:end, p].max())
                found.append((end, Tag("sprint", pid, int(self.side[p]), round(peak, 1), int(tr.period[end]), 0.0)))
            passed = np.flatnonzero(self.distance_m[:, p] >= DISTANCE_KM * 1000.0)
            if len(passed):
                f = int(passed[0])
                found.append((f, Tag("distance", pid, int(self.side[p]), DISTANCE_KM, int(tr.period[f]), 0.0)))
        found.sort(key=lambda item: (item[0], item[1].kind, item[1].player_id))
        tags = []
        best = 0.0
        for f, tag in found:
            record = tag.kind == "sprint" and tag.value > best
            if tag.kind == "sprint":
                best = max(best, tag.value)
            tags.append(
                Tag(tag.kind, tag.player_id, tag.side, tag.value, tag.period, round(float(tr.t[f]), 1), record=record)
            )
        return tags

    def tags_between(self, after: int | None, upto: int) -> list[Tag]:
        """Tags that fell due after frame `after` (None: from the start) up to and including `upto`."""
        lo = -1 if after is None else after
        return [tag for tag, f in zip(self.tags, self._tag_frames, strict=True) if lo < f <= upto]

    def player_at(self, frame: int, player_id: str) -> tuple[float, float] | None:
        """(distance in km, top speed in km/h) for the player by `frame`."""
        try:
            p = self.player_ids.index(player_id)
        except ValueError:
            return None
        return float(self.distance_m[frame, p]) / 1000.0, float(self.top_kmh[frame, p])

    def team_distance_km(self, frame: int, side: int) -> float:
        return float(self.distance_m[frame, self.side == side].sum()) / 1000.0
