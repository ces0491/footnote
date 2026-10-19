"""Match stats from the feed, counted the way a broadcast stats graphic counts them.

- Passes: attempted and completed, throw-ins excluded. Accuracy is completed over attempted.
- Possession: each side's share of those passes, the broadcast convention, rather than time on the
  ball.
- Shots: every attempt except the shot behind a goal that VAR rules out. On target means scored or
  saved.
- Corners taken, fouls committed and offsides. Cards: a second yellow counts as a yellow and a red.

The score is the provider's: the latest `score` carried by a goal, a completed VAR check, the end of
a period, or a correction.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

_SCORE_CARRIERS = frozenset({"goal", "var_check", "period_end", "match_end"})


@dataclass
class TeamStats:
    shots: int = 0
    on_target: int = 0
    passes: int = 0
    passes_completed: int = 0
    corners: int = 0
    fouls: int = 0
    offsides: int = 0
    yellow_cards: int = 0
    red_cards: int = 0


@dataclass
class MatchStats:
    home_id: str
    away_id: str
    score: dict[str, int] = field(default_factory=lambda: {"home": 0, "away": 0})
    teams: dict[str, TeamStats] = field(default_factory=dict)
    # Shot event ID -> (team, on target), and goal event ID -> the event it came from, so a goal VAR
    # rules out can take its shot back off the count.
    _shots: dict[str, tuple[str, bool]] = field(default_factory=dict, repr=False)
    _goal_sources: dict[str, str] = field(default_factory=dict, repr=False)
    _ruled_out: set[str] = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        for team_id in (self.home_id, self.away_id):
            self.teams.setdefault(team_id, TeamStats())

    def apply(self, m: dict) -> None:
        kind = m["type"]
        if kind in _SCORE_CARRIERS and isinstance(m.get("score"), dict):
            self.score = {"home": m["score"]["home"], "away": m["score"]["away"]}
        elif kind == "amendment" and isinstance(m["corrected_event"].get("score"), dict):
            corrected = m["corrected_event"]["score"]
            self.score = {"home": corrected["home"], "away": corrected["away"]}

        team = self.teams.get(m.get("team_id", ""))
        if kind == "goal":
            self._goal_sources[m["event_id"]] = m["from_event_id"]
        elif kind == "var_check":
            if m["status"] == "complete" and m.get("decision") == "no_goal" and m.get("goal_event_id"):
                self._rule_out(m["goal_event_id"])
        elif team is None:
            return
        elif kind == "pass" and m["pass_type"] != "throw_in":
            team.passes += 1
            team.passes_completed += m["outcome"] == "complete"
            team.corners += m["pass_type"] == "corner"
        elif kind == "shot":
            on_target = m["outcome"] in ("goal", "saved")
            team.shots += 1
            team.on_target += on_target
            self._shots[m["event_id"]] = (m["team_id"], on_target)
        elif kind == "foul":
            team.fouls += 1
        elif kind == "offside":
            team.offsides += 1
        elif kind == "card":
            team.yellow_cards += m["card"] in ("yellow", "second_yellow")
            team.red_cards += m["card"] in ("red", "second_yellow")

    def _rule_out(self, goal_event_id: str) -> None:
        shot_id = self._goal_sources.get(goal_event_id)
        if shot_id is None or shot_id in self._ruled_out or shot_id not in self._shots:
            return
        team_id, on_target = self._shots[shot_id]
        self.teams[team_id].shots -= 1
        self.teams[team_id].on_target -= on_target
        self._ruled_out.add(shot_id)

    def view(self) -> dict:
        """Counters per team plus the derived figures, keyed by club ID."""
        total_passes = sum(t.passes for t in self.teams.values())
        teams = {}
        for team_id, t in self.teams.items():
            teams[team_id] = asdict(t) | {
                "pass_accuracy": round(t.passes_completed / t.passes, 3) if t.passes else None,
                "possession": round(t.passes / total_passes, 3) if total_passes else None,
            }
        return {"score": dict(self.score), "teams": teams}
