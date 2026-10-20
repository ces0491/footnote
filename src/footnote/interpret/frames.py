"""Which way each side attacks, and positions in a side's own frame.

The feed's coordinates are absolute (x 0-105 m along the pitch, y 0-68 m across). In a side's frame,
u is progress towards the opponent's goal and v runs across the pitch; a side attacking towards
x = 0 sees the pitch turned through a half-turn. The match metadata records each side's direction
per half (`lineups[].attacking_direction`).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

LENGTH = 105.0
WIDTH = 68.0
HALF_WIDTH = WIDTH / 2
BOX_DEPTH = 16.5
BOX_HALF_WIDTH = 20.16


@dataclass(frozen=True)
class Frames:
    home_id: str
    away_id: str
    # (side, period) -> +1 attacking towards x = 105, -1 towards x = 0; side 0 is home.
    directions: dict[tuple[int, int], int]

    @classmethod
    def from_meta(cls, meta: dict) -> Frames:
        home_id, away_id = str(meta["home"]["id"]), str(meta["away"]["id"])
        directions: dict[tuple[int, int], int] = {}
        for lineup in meta["lineups"]:
            side = 0 if lineup["club_id"] == home_id else 1
            for period, key in ((1, "first_half"), (2, "second_half")):
                directions[(side, period)] = 1 if lineup["attacking_direction"][key] == "+x" else -1
        return cls(home_id, away_id, directions)

    def side(self, team_id: object) -> int | None:
        """0 for the home club, 1 for the away club, None for anything else."""
        if team_id == self.home_id:
            return 0
        if team_id == self.away_id:
            return 1
        return None

    def u(self, side: int, period: int, x: float) -> float:
        """Progress towards the opponent's goal, in metres from the side's own goal line."""
        return x if self.directions[(side, period)] == 1 else LENGTH - x

    def to_frame(self, side: int, period: int, xy: np.ndarray) -> np.ndarray:
        """Absolute positions (..., 2) in the side's frame; NaNs stay NaN."""
        out = np.array(xy, dtype=float, copy=True)
        if self.directions[(side, period)] == -1:
            out[..., 0] = LENGTH - out[..., 0]
            out[..., 1] = WIDTH - out[..., 1]
        return out


def in_box(u: float, v: float) -> bool:
    """Inside the opponent's penalty area, in a side's frame."""
    return u >= LENGTH - BOX_DEPTH and abs(v - HALF_WIDTH) <= BOX_HALF_WIDTH
