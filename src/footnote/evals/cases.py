"""The agents' jobs on the showcase match, as the processor queues them.

A replay from kick-off queues every card an agent drafts, in the order they are found, and a card a
correction restates once more with its new facts. A replay from each of the other jump points
(docs/experience.md, "The judges' path") also opens with a catch-up. Each job is a case, served to the
writer through the real match tools from an in-memory store: each case is a run of its own, so the
two states of one insight (the 81st-minute goal before and after its correction) don't meet.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

from footnote.live.analysis import Analysis
from footnote.live.match import Match
from footnote.live.state import RunState
from footnote.live.timeline import Timeline
from footnote.replayer.schedule import plan

JUMPS = (23, 31, 60, 81)  # the jump points that start mid-match


@dataclass(frozen=True)
class Case:
    key: str  # the insight and its facts version, or the catch-up and its jump point
    row: dict  # the insight as the store holds it when the job is queued

    @property
    def insight_id(self) -> str:
        return str(self.row["insight_id"])

    @property
    def kind(self) -> str:
        return str(self.row["kind"])

    @property
    def topic(self) -> str:
        return str(self.row["topic"])

    @property
    def facts_version(self) -> int:
        return int(self.row["facts_version"])


def cases(match: Match, analysis: Analysis) -> list[Case]:
    out: list[Case] = []
    state = RunState(match.match_id, match.home_id, match.away_id, analysis)
    for m in match.feed:
        state.apply(m)
        for change in state.insight_changes():
            insight = change.insight
            if insight.agent and change.what in ("new", "restated"):
                key = f"{insight.insight_id}/v{insight.facts_version}"
                out.append(Case(key, copy.deepcopy(insight.record())))
    timeline = Timeline.from_feed(match.feed)
    for minute in JUMPS:
        backfill_seq = plan(match.feed, timeline, timeline.jump_point(minute), 1.0).backfill_seq
        state = RunState.rebuild(
            match.match_id, match.home_id, match.away_id, match.feed[:backfill_seq], analysis, backfill_seq
        )
        assert state.book is not None
        out.append(Case(f"catchup@{minute}", copy.deepcopy(state.book.insights["catchup"].record())))
    return out


class CaseSource:
    """The match tools' store (footnote.tools.scope.Source) for the cases: the run ID is the case's key."""

    def __init__(self, match: Match, all_cases: list[Case]) -> None:
        self.rows = {c.key: c.row for c in all_cases}
        self.messages = match.feed

    async def insight(self, run_id: str, insight_id: str) -> dict | None:
        row = self.rows.get(run_id)
        return row if row is not None and row["insight_id"] == insight_id else None

    async def feed(self, run_id: str, upto_seq: int) -> list[dict]:
        return [m for m in self.messages if m["seq"] <= upto_seq]
