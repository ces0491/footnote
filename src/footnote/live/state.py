"""A run's match state: the projection of its feed that viewers see.

The processor folds each feed message into a RunState and stores the view after every batch.
Viewers get the score, phase, clock and stats with every pushed event, so a missed push is never
stale for long. The stored feed is the source of truth: after a restart the processor rebuilds a
run's state by folding the run's stored messages again.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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
    seq: int = 0
    phase: str = "pre_match"
    clock: dict | None = None
    stats: MatchStats = field(init=False)
    key_events: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.stats = MatchStats(self.home_id, self.away_id)

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
        if m["type"] in KEY_EVENT_TYPES:
            self.key_events.append(client_event(m))
        return True

    def live_fields(self) -> dict:
        """What every pushed event carries: everything but the key-event history."""
        return {"seq": self.seq, "phase": self.phase, "clock": self.clock} | self.stats.view()

    def view(self) -> dict:
        return self.live_fields() | {"key_events": list(self.key_events)}

    @classmethod
    def rebuild(cls, match_id: str, home_id: str, away_id: str, feed: list[dict]) -> RunState:
        state = cls(match_id, home_id, away_id)
        for m in feed:
            state.apply(m)
        return state
