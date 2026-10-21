"""A run's insights, and what happens to them after they're found.

An insight starts as what the moment finder found (moments.py), worded by its template. Later
messages can change it:

- A VAR check completes: the card saying it had started leaves the shortlist.
- VAR rules a goal out: every insight citing the goal is flagged and leaves the shortlist, such as
  the goal's own card and the one on the pass that set it up.
- The provider amends an event: every insight citing the event is flagged; one whose facts came from
  the event is restated with the corrected facts, as a new version the agents draft again; and a
  correction insight tells viewers what changed (docs/audience.md, P2).

A replay that starts mid-match gets one more insight at the end of its backfill: the catch-up on
what its viewers missed (docs/audience.md, P7). It is live, unlike the history it sums up.

`InsightBook.observe` runs once per message, after the run's state has applied it, and keeps what
changed for the processor to store and push (`changes`). The store numbers the versions, because
the agents add theirs to the same insights (footnote.agents).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from footnote.insights.draft import Card, Draft, render
from footnote.insights.facts import Facts, facts_to_json
from footnote.insights.moments import (
    AGENT_TOPICS,
    ANIMATED_KINDS,
    DURATION,
    HOLD_FOR_STOPPAGE,
    PLACEMENT,
    PLACEMENT_BY_TOPIC,
    Found,
    MomentFinder,
)
from footnote.insights.templates import template

if TYPE_CHECKING:
    from footnote.live.state import RunState

# new: found. flagged: VAR or a correction undid what it cites. restated: new facts after a
# correction. ended: off the shortlist sooner than its shelf life, its moment being over.
ChangeKind = Literal["new", "flagged", "restated", "ended"]

TICK = 0.01  # the feed's times are kept to the hundredth of a second


@dataclass
class Insight:
    insight_id: str
    kind: str
    topic: str
    seq: int  # the feed seq its facts are as of
    at: dict
    until: dict
    rank: float
    reason: str
    evidence: list[str]
    facts: Facts
    agent: bool  # whether the agents draft it
    live: bool  # False for a moment the run's backfill passed: history, not for air
    corrects: str | None = None
    flag: dict | None = None
    facts_version: int = 1

    @classmethod
    def start(cls, found: Found, live: bool) -> Insight:
        return cls(
            insight_id=found.insight_id,
            kind=found.kind,
            topic=found.topic,
            seq=found.seq,
            at=found.at,
            until=found.until,
            rank=found.rank,
            reason=found.reason,
            evidence=found.evidence,
            facts=found.facts,
            agent=live and found.topic in AGENT_TOPICS,
            live=live,
            corrects=found.corrects,
        )

    @property
    def placement(self) -> str:
        return PLACEMENT_BY_TOPIC.get(self.topic) or PLACEMENT.get(self.kind, "side_panel")

    @property
    def hold(self) -> str | None:
        return "stoppage" if self.kind in HOLD_FOR_STOPPAGE else None

    @property
    def duration(self) -> float | None:
        return DURATION.get(self.placement)

    @property
    def motion(self) -> str:
        return "animated" if self.kind in ANIMATED_KINDS else "still"

    @property
    def template(self) -> Draft:
        return template(self.topic, self.facts)

    def card(self) -> Card:
        return render(self.template, self.facts)

    def record(self) -> dict:
        """The fields the store keeps for the insight, beside its versions."""
        return {
            "insight_id": self.insight_id,
            "kind": self.kind,
            "topic": self.topic,
            "seq": self.seq,
            "at": self.at,
            "until": self.until,
            "rank": self.rank,
            "reason": self.reason,
            "evidence": self.evidence,
            "placement": self.placement,
            "hold": self.hold,
            "duration": self.duration,
            "motion": self.motion,
            "corrects": self.corrects,
            "live": self.live,
            "flag": self.flag,
            "facts": facts_to_json(self.facts),
            "facts_version": self.facts_version,
            "template": self.template.model_dump(),
            "agent": self.agent,
        }


@dataclass(frozen=True)
class Change:
    insight: Insight
    what: ChangeKind


@dataclass
class InsightBook:
    finder: MomentFinder
    insights: dict[str, Insight] = field(default_factory=dict)
    _changes: list[Change] = field(default_factory=list)

    @classmethod
    def for_match(cls, meta: dict) -> InsightBook:
        return cls(MomentFinder(meta))

    def observe(self, m: dict, state: RunState, live: bool, opens: bool = False) -> None:
        """Take in one message. `opens` marks the last message of the backfill of a replay that
        starts mid-match: its viewers get a catch-up on the match so far."""
        changes: list[Change] = []
        if m["type"] == "amendment":
            changes += self._amend(m, live)
        found_now = self.finder.observe(m, state)
        if opens:
            found_now.append(self.finder.catch_up(m, state))
        for found in found_now:
            if found.insight_id in self.insights:
                continue
            # The catch-up is for the run's own viewers, so it is live although its message isn't.
            insight = Insight.start(found, live or found.topic == "catch_up")
            self.insights[insight.insight_id] = insight
            changes.append(Change(insight, "new"))
        if m["type"] == "var_check" and m["status"] == "complete":
            changes += self._decided(m)
        self._changes = changes

    def changes(self) -> list[Change]:
        """What the last message changed."""
        return list(self._changes)

    def _flag(self, m: dict, reason: str) -> dict:
        return {"reason": reason, "event_id": m["event_id"], "version": m["version"], "seq": m["seq"]}

    def _decided(self, m: dict) -> list[Change]:
        """A VAR check is over. Its started card ends, and a goal it ruled out takes every insight
        citing the goal off the shortlist with it, flagged so the producer sees what it undid."""
        changes: list[Change] = []
        now = {"period": m["period"], "t": m["t"]}
        started_id = f"var-{m['related_event_id']}" if m.get("related_event_id") else None
        started = self.insights.get(started_id) if started_id else None
        if started is not None and started.topic == "var_started" and _before(now, started.until):
            # Off just before the decision: play stays stopped at the decision's time for a while
            # (half a minute in the showcase), and `until` is the last moment a card is current.
            started.until = {"period": m["period"], "t": round(m["t"] - TICK, 2)}
            changes.append(Change(started, "ended"))
        goal_event = m.get("goal_event_id")
        if m.get("decision") != "no_goal" or not goal_event:
            return changes
        own = {f"var-{m['event_id']}", started_id}
        for insight in self.insights.values():
            if insight.insight_id in own or goal_event not in insight.evidence or insight.flag is not None:
                continue
            ruled_out = insight.insight_id == f"goal-{goal_event}"
            insight.flag = self._flag(m, "Ruled out by VAR" if ruled_out else "The goal it cites was ruled out by VAR")
            insight.until = now
            changes.append(Change(insight, "flagged"))
        return changes

    def _amend(self, m: dict, live: bool) -> list[Change]:
        amended = m["event_id"]
        corrected = m["corrected_event"]
        reason = f"The provider amended the {m['amends']} this cites: {m.get('reason', 'no reason given')}"
        changes: list[Change] = []
        restated_goal: str | None = None
        for insight in self.insights.values():
            if amended not in insight.evidence:
                continue
            insight.flag = self._flag(m, reason)
            context = self.finder.goals.get(amended)
            if insight.insight_id == f"goal-{amended}" and corrected["type"] == "goal" and context is not None:
                found = self.finder.goal_insight(corrected, context, m["seq"])
                insight.topic, insight.seq, insight.facts = found.topic, m["seq"], found.facts
                insight.evidence = list(dict.fromkeys([*found.evidence, amended]))
                insight.facts_version += 1
                restated_goal = insight.insight_id
                changes.append(Change(insight, "restated"))
            else:
                changes.append(Change(insight, "flagged"))
        found = self.finder.correction(m, restated_goal)
        if found.insight_id not in self.insights:
            insight = Insight.start(found, live)
            self.insights[insight.insight_id] = insight
            changes.append(Change(insight, "new"))
        return changes


def _before(a: dict, b: dict) -> bool:
    """Whether match time `a` comes before `b`."""
    return (a["period"], a["t"]) < (b["period"], b["t"])
