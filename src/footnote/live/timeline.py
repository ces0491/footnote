"""Replay time: how far into a match a message or a moment is, with the half-time break shortened.

The feed's timestamps run on the wall clock: kick-off, the first half, a fifteen-minute break, the
second half, and any corrections issued after the final whistle. A replay keeps that pacing but
shortens the break, so nobody waits fifteen minutes for the second half. Replay seconds count from
kick-off along the shortened timeline.

The replayer publishes each message at its replay second, scaled by the run's speed. Viewers'
clients get `first_half_end` and `half_time` in the run descriptor and use the same mapping to turn
their own playback position into a period and a time in it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

DEFAULT_HALF_TIME = 30.0  # replay seconds the half-time break is shortened to
DEFAULT_LEAD_IN = 30.0  # replay seconds a jump starts before the minute it jumps to


def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


@dataclass(frozen=True)
class Timeline:
    kickoff: datetime  # wall time of the first-half kick-off
    first_half_end: float  # wall seconds from kick-off to the first half's final whistle
    second_half_start: float  # wall seconds from kick-off to the second-half kick-off
    half_time: float = DEFAULT_HALF_TIME

    @classmethod
    def from_feed(cls, feed: list[dict], half_time: float = DEFAULT_HALF_TIME) -> Timeline:
        starts = {m["period"]: parse_ts(m["ts"]) for m in feed if m["type"] == "period_start"}
        first_end = next(m for m in feed if m["type"] == "period_end" and m["period"] == 1)
        kickoff = starts[1]
        return cls(
            kickoff=kickoff,
            first_half_end=(parse_ts(first_end["ts"]) - kickoff).total_seconds(),
            second_half_start=(starts[2] - kickoff).total_seconds(),
            half_time=half_time,
        )

    def replay_seconds(self, ts: str) -> float:
        """Replay seconds from kick-off to a feed timestamp; negative before kick-off."""
        wall = (parse_ts(ts) - self.kickoff).total_seconds()
        if wall <= self.first_half_end:
            return wall
        if wall < self.second_half_start:
            through_break = (wall - self.first_half_end) / (self.second_half_start - self.first_half_end)
            return self.first_half_end + through_break * self.half_time
        return self.first_half_end + self.half_time + (wall - self.second_half_start)

    def at(self, period: int, t: float) -> float:
        """Replay seconds of the moment `t` seconds into `period`."""
        return t if period == 1 else self.first_half_end + self.half_time + t

    def moment(self, replay: float) -> tuple[int, float] | None:
        """The period and seconds into it that a replay second shows, or None during the break."""
        if replay <= self.first_half_end:
            return 1, replay
        if replay < self.first_half_end + self.half_time:
            return None
        return 2, replay - self.first_half_end - self.half_time

    def jump_point(self, minute: int, lead_in: float = DEFAULT_LEAD_IN) -> float:
        """Where to start a replay so the broadcast minute `minute` begins `lead_in` seconds in.

        The lead-in never reaches back past the start of the period, so a jump to 46' starts at the
        second-half kick-off.
        """
        if not 1 <= minute <= 90:
            raise ValueError(f"minute must be 1-90, got {minute}")
        period = 1 if minute <= 45 else 2
        t = (minute - 1 - (0 if period == 1 else 45)) * 60.0
        return self.at(period, max(0.0, t - lead_in))

    def describe(self) -> dict[str, float]:
        """What a client needs to place its playback: see `moment`."""
        return {"first_half_end": self.first_half_end, "half_time": self.half_time}
