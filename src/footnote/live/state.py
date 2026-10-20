"""A run's match state: the projection of its feed that viewers see.

The processor folds each feed message into a RunState and stores the view after every batch.
Viewers get the score, phase, clock, stats and match state with every pushed event, so a missed push
is never stale for long. The stored feed is the source of truth: after a restart the processor
rebuilds a run's state by folding the run's stored messages again.

With an `Analysis` the state also carries what the models work out (live/analysis.py): pass
difficulty, the match state and its timeline, per-player lines, distances, speeds and tags. Without
one it carries the counts alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from footnote.live.analysis import Analysis, RunAnalysis
from footnote.live.contract import client_event
from footnote.live.stats import MatchStats

# Events listed on the match ticker and kept in the snapshot.
KEY_EVENT_TYPES = frozenset(
    {
        "goal",
        "shot",
        "var_check",
        "card",
        "substitution",
        "offside",
        "injury",
        "added_time",
        "period_start",
        "period_end",
        "match_end",
        "amendment",
    }
)

_PHASE_AFTER = {
    ("period_start", 1): "first_half",
    ("period_end", 1): "half_time",
    ("period_start", 2): "second_half",
    ("match_end", 2): "full_time",
}


@dataclass
class RunState:
    match_id: str
    home_id: str
    away_id: str
    analysis: Analysis | None = None
    seq: int = 0
    phase: str = "pre_match"
    clock: dict | None = None
    stats: MatchStats = field(init=False)
    insight: RunAnalysis | None = field(init=False)
    key_events: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.stats = MatchStats(self.home_id, self.away_id)
        self.insight = RunAnalysis(self.analysis) if self.analysis is not None else None

    def apply(self, m: dict) -> bool:
        """Fold one feed message in. Returns False for a message already applied (redelivery)."""
        if m["seq"] <= self.seq:
            return False
        self.seq = m["seq"]
        self.phase = _PHASE_AFTER.get((m["type"], m["period"]), self.phase)
        if m["type"] != "amendment":
            # A correction carries the clock of when it was issued, which is no news about the match.
            self.clock = {k: m[k] for k in ("period", "t", "clock", "minute", "added_minute")}
        self.stats.apply(m)
        if self.insight is not None:
            self.insight.apply(m)
        if m["type"] in KEY_EVENT_TYPES:
            self.key_events.append(client_event(m))
        return True

    def live_fields(self) -> dict:
        """What every pushed event carries: everything but the histories."""
        stats = self.stats.view()
        out = {"seq": self.seq, "phase": self.phase, "clock": self.clock} | stats
        if self.insight is not None:
            for side, team_id in enumerate((self.home_id, self.away_id)):
                stats["teams"][team_id] |= self.insight.team_fields(side)
            out["match_state"] = self.insight.match_state
        return out

    def push_fields(self) -> dict:
        """What an event push carries beside the event: the live fields, and what the event added."""
        extras = self.insight.extras() if self.insight is not None else {}
        return self.live_fields() | extras

    def view(self) -> dict:
        out = self.live_fields() | {"key_events": list(self.key_events)}
        if self.insight is not None:
            out |= self.insight.view()
        return out

    @classmethod
    def rebuild(
        cls, match_id: str, home_id: str, away_id: str, feed: list[dict], analysis: Analysis | None = None
    ) -> RunState:
        state = cls(match_id, home_id, away_id, analysis)
        for m in feed:
            state.apply(m)
        return state
