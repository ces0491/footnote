"""When each message of a run goes out."""

from __future__ import annotations

from dataclasses import dataclass

from footnote.live.timeline import Timeline


@dataclass(frozen=True)
class Step:
    offset: float  # wall seconds after the run's start
    messages: list[dict]  # published together, in feed order


@dataclass(frozen=True)
class Plan:
    backfill: list[dict]  # sent at once, before the start
    steps: list[Step]

    @property
    def backfill_seq(self) -> int:
        """seq of the last backfilled message; 0 when the run starts before the first message."""
        return self.backfill[-1]["seq"] if self.backfill else 0


def plan(feed: list[dict], timeline: Timeline, start_replay: float, speed: float) -> Plan:
    """Split the feed at `start_replay` and time the rest; messages sharing a timestamp share a step."""
    if speed <= 0:
        raise ValueError("speed must be positive")
    backfill: list[dict] = []
    steps: list[Step] = []
    previous = float("-inf")
    for m in feed:
        replay = timeline.replay_seconds(m["ts"])
        if replay < previous:
            raise ValueError(f"feed out of order at seq {m['seq']}")
        previous = replay
        if replay < start_replay:
            backfill.append(m)
            continue
        offset = (replay - start_replay) / speed
        if steps and steps[-1].offset == offset:
            steps[-1].messages.append(m)
        else:
            steps.append(Step(offset, [m]))
    return Plan(backfill, steps)
