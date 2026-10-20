"""What a run works out beyond counting: pass difficulty, the match state, distances, speeds and tags.

`Analysis` is what every run of a match shares: the match metadata, the attacking directions, the
tracking and the fitted models (`footnote.interpret`). `RunAnalysis` is one run's share of the work, folded message
by message beside the counts in `RunState`, so a run rebuilt from its stored feed reaches the same
view. It adds:

- each pass's difficulty, on the pushed event and in the passer's line;
- per side: average pass length and difficulty (throw-ins excluded, as in the pass count), distance
  covered, and the fastest shot;
- per player: passes, completions, average and hardest difficulty, distance covered, top speed;
- the match state as of the model's lag, and a timeline of it;
- tags from the tracking: sprints and distance milestones.

The timeline is built from the state after each message, so a viewer who folds the state each push
carries into the snapshot's timeline arrives at the same timeline (`timeline_after`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from footnote.interpret import difficulty
from footnote.interpret.difficulty import DifficultyModel
from footnote.interpret.frames import Frames
from footnote.interpret.physical import Physical, Tag, Tracking
from footnote.interpret.shape import per_second
from footnote.interpret.state import LABELS, SIDE_OF_LABEL, Estimate, StateModel, StateTracker
from footnote.live.match import Match, data_dir
from footnote.live.timeline import broadcast_minute

_HOME_STATES = [i for i, side in enumerate(SIDE_OF_LABEL) if side == 0]
_AWAY_STATES = [i for i, side in enumerate(SIDE_OF_LABEL) if side == 1]


@dataclass(frozen=True)
class Analysis:
    meta: dict  # the match metadata: clubs and line-ups, for naming what the insights state
    frames: Frames
    tracking: Tracking
    physical: Physical
    shape: dict[int, np.ndarray]  # each side's shape, second by second (interpret/shape.py)
    difficulty: DifficultyModel
    state_model: StateModel

    @classmethod
    def load(cls, match: Match, root: Path | None = None) -> Analysis:
        tracking = Tracking.load((root or data_dir()) / "matches" / match.match_id / "tracking.npz")
        frames = Frames.from_meta(match.meta)
        return cls(
            meta=match.meta,
            frames=frames,
            tracking=tracking,
            physical=Physical(tracking, match.home_id, match.away_id),
            shape=per_second(tracking, frames),
            difficulty=DifficultyModel.load(),
            state_model=StateModel.load(),
        )

    def pass_difficulty(self, m: dict) -> float | None:
        x = difficulty.features(m, self.frames, self.tracking.positions(int(m["period"]), float(m["t"])))
        if x is None:
            return None
        return round(1.0 - float(self.difficulty.completion(x)[0]), 3)


def state_summary(estimate: Estimate, frames: Frames) -> dict:
    """The match state a viewer is shown, the model's chance of it, and which side is on top."""
    belief = estimate.belief
    i = estimate.shown
    state, _, side = LABELS[i].partition(":")
    return {
        "period": estimate.period,
        "second": estimate.second,
        "state": state,
        "team_id": frames.home_id if side == "home" else frames.away_id if side == "away" else None,
        "confidence": round(float(belief[i]), 2),
        "on_top": {
            "home": round(float(belief[_HOME_STATES].sum()), 2),
            "away": round(float(belief[_AWAY_STATES].sum()), 2),
        },
    }


def timeline_after(timeline: list[dict], state: dict | None) -> list[dict]:
    """The state timeline once `state` is folded in: the last spell extends, or a new one starts.

    The browser applies the same rule to each push (frontend/src/lib/live/run-reducer.ts).
    """
    if state is None:
        return timeline
    last = timeline[-1] if timeline else None
    if last and (last["period"], last["state"], last["team_id"]) == (state["period"], state["state"], state["team_id"]):
        if last["end"] == state["second"]:
            return timeline
        return [*timeline[:-1], {**last, "end": state["second"]}]
    spell = {
        "period": state["period"],
        "state": state["state"],
        "team_id": state["team_id"],
        "start": state["second"],
        "end": state["second"],
    }
    return [*timeline, spell]


@dataclass
class _Passing:
    passes: int = 0
    completed: int = 0
    length: float = 0.0
    difficulty: float = 0.0
    rated: int = 0
    hardest: float | None = None
    hardest_event_id: str | None = None
    hardest_minute: int | None = None

    def add(self, m: dict, rating: float | None) -> None:
        self.passes += 1
        self.completed += m["outcome"] == "complete"
        self.length += float(m["length"])
        if rating is None:
            return
        self.rated += 1
        self.difficulty += rating
        if self.hardest is None or rating > self.hardest:
            self.hardest, self.hardest_event_id, self.hardest_minute = rating, m["event_id"], int(m["minute"])


@dataclass
class _Side:
    passing: _Passing = field(default_factory=_Passing)
    top_shot_kmh: float | None = None


class RunAnalysis:
    def __init__(self, analysis: Analysis) -> None:
        self.analysis = analysis
        self.tracker = StateTracker(analysis.frames, analysis.shape, analysis.state_model)
        self.match_state: dict | None = None
        self.timeline: list[dict] = []
        self.sides = (_Side(), _Side())
        self.players: dict[str, _Passing] = {}
        self.tags: list[dict] = []
        self.frame: int | None = None  # the last tracking frame this run has reached
        # The state shown for every second estimated so far, by period, as an index into LABELS. The
        # timeline above only takes the state after each message, so it skips seconds when no
        # message came (stoppages); the insights measure spells over every second (shown_between).
        self.shown: dict[int, list[int]] = {}
        self._extras: dict = {}

    def apply(self, m: dict) -> None:
        a = self.analysis
        extras: dict = {}
        estimates = self.tracker.observe(m)
        for estimate in estimates:
            self.shown.setdefault(estimate.period, []).append(estimate.shown)
        if estimates and self.tracker.latest is not None:
            self.match_state = state_summary(self.tracker.latest, a.frames)
        self.timeline = timeline_after(self.timeline, self.match_state)
        if m["type"] not in ("match_info", "amendment"):
            frame = a.tracking.frame(int(m["period"]), float(m["t"]))
            if frame is not None and (self.frame is None or frame > self.frame):
                new = [self._tag(tag) for tag in a.physical.tags_between(self.frame, frame)]
                self.frame = frame
                if new:
                    self.tags += new
                    extras["tags"] = new
        side = a.frames.side(m.get("team_id"))
        if m["type"] == "pass" and side is not None and m["pass_type"] != "throw_in":
            rating = a.pass_difficulty(m)
            self.sides[side].passing.add(m, rating)
            self.players.setdefault(m["player_id"], _Passing()).add(m, rating)
            extras["difficulty"] = rating
        elif m["type"] == "shot" and side is not None:
            speed = float(m["speed_kmh"])
            best = self.sides[side].top_shot_kmh
            self.sides[side].top_shot_kmh = speed if best is None else max(best, speed)
        if side is not None and m.get("player_id") and m["type"] != "goal":
            extras["player"] = self.player_line(str(m["player_id"]))
        self._extras = extras

    def _tag(self, tag: Tag) -> dict:
        minute, added = broadcast_minute(tag.period, tag.t)
        team_id = self.analysis.frames.home_id if tag.side == 0 else self.analysis.frames.away_id
        return {
            "kind": tag.kind,
            "player_id": tag.player_id,
            "team_id": team_id,
            "value": tag.value,
            "unit": tag.unit,
            "period": tag.period,
            "t": tag.t,
            "minute": minute,
            "added_minute": added,
            "record": tag.record,
        }

    def player_line(self, player_id: str) -> dict:
        p = self.players.get(player_id, _Passing())
        line: dict = {
            "player_id": player_id,
            "passes": p.passes,
            "completed": p.completed,
            "difficulty": round(p.difficulty / p.rated, 2) if p.rated else None,
            "hardest": None if p.hardest is None else round(p.hardest, 2),
            "hardest_minute": p.hardest_minute,
        }
        physical = None if self.frame is None else self.analysis.physical.player_at(self.frame, player_id)
        if physical is not None:
            line["distance_km"], line["top_speed_kmh"] = round(physical[0], 2), round(physical[1], 1)
        return line

    def team_fields(self, side: int) -> dict:
        s = self.sides[side]
        p = s.passing
        distance = None if self.frame is None else round(self.analysis.physical.team_distance_km(self.frame, side), 1)
        return {
            "pass_length": round(p.length / p.passes, 1) if p.passes else None,
            "pass_difficulty": round(p.difficulty / p.rated, 2) if p.rated else None,
            "distance_km": distance,
            "top_shot_kmh": s.top_shot_kmh,
        }

    def extras(self) -> dict:
        """What the last message added, for its push: a pass's difficulty, the player's line, tags."""
        return dict(self._extras)

    def shown_between(self, period: int, start: int, end: int) -> list[str]:
        """The state shown each second of `period` from `start` up to `end`, as labels."""
        seconds = self.shown.get(period, [])
        return [LABELS[i] for i in seconds[max(0, start) : max(0, end)]]

    def view(self) -> dict:
        players = sorted(set(self.players) | set(self.analysis.physical.player_ids))
        return {
            "state_timeline": list(self.timeline),
            "players": {pid: self.player_line(pid) for pid in players},
            "tags": list(self.tags),
        }
