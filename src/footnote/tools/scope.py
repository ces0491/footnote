"""A tool call's scope: one insight of one run, and the match as of that insight.

The agents service names the run and the insight in the `x-footnote-run` and `x-footnote-insight`
headers of every request to the match tools; the model choosing the tool calls never sees them.
`Scopes.get` loads the insight's row and the run's stored feed up to the insight's seq, and folds
the feed with the processor's code (live/state.py) on a worker thread. It keeps the last few folds
by run and seq, so the calls of one agent run fold the feed once, and so do the drafts of two
insights from the same message (a correction and the goal it restates).
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from typing import Protocol

from footnote.insights.moments import MomentFinder
from footnote.live.analysis import Analysis
from footnote.live.match import Match
from footnote.live.state import RunState

RUN_HEADER = "x-footnote-run"
INSIGHT_HEADER = "x-footnote-insight"


class Source(Protocol):
    async def insight(self, run_id: str, insight_id: str) -> dict | None:
        """The insight's row: kind, topic, seq, facts, facts_version, template, evidence and the rest."""
        ...

    async def feed(self, run_id: str, upto_seq: int) -> list[dict]:
        """The run's stored feed up to and including `upto_seq`, in seq order."""
        ...


@dataclass(frozen=True)
class Scope:
    run_id: str
    insight: dict
    state: RunState  # the run as of the insight's seq
    feed: list[dict]

    @property
    def finder(self) -> MomentFinder:
        assert self.state.book is not None
        return self.state.book.finder

    @property
    def events(self) -> dict[str, dict]:
        """Each event as it stands at the insight's seq, corrections applied."""
        out: dict[str, dict] = {}
        for m in self.feed:
            if m["type"] == "amendment":
                out[m["event_id"]] = {**m["corrected_event"], "seq": m["seq"]}
            elif m["type"] != "match_info":
                out[m["event_id"]] = m
        return out


class Scopes:
    def __init__(self, source: Source, match: Match, analysis: Analysis, keep: int = 8) -> None:
        self.source = source
        self.match = match
        self.analysis = analysis
        self.keep = keep
        self._folds: OrderedDict[tuple[str, int], asyncio.Task[tuple[RunState, list[dict]]]] = OrderedDict()

    async def get(self, run_id: str, insight_id: str) -> Scope:
        row = await self.source.insight(run_id, insight_id)
        if row is None:
            raise LookupError(f"no insight {insight_id} in run {run_id}")
        state, feed = await self._fold(run_id, int(row["seq"]))
        return Scope(run_id, row, state, feed)

    async def _fold(self, run_id: str, seq: int) -> tuple[RunState, list[dict]]:
        key = (run_id, seq)
        task = self._folds.get(key)
        if task is None:
            task = asyncio.create_task(self._load(run_id, seq))
            self._folds[key] = task
            while len(self._folds) > self.keep:
                self._folds.popitem(last=False)
        else:
            self._folds.move_to_end(key)
        try:
            return await asyncio.shield(task)
        except Exception:
            self._folds.pop(key, None)
            raise

    async def _load(self, run_id: str, seq: int) -> tuple[RunState, list[dict]]:
        feed = await self.source.feed(run_id, seq)
        m = self.match
        state = await asyncio.to_thread(RunState.rebuild, m.match_id, m.home_id, m.away_id, feed, self.analysis)
        return state, feed
