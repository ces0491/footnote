"""The match tools: each answers as of its insight's moment, with facts code computed."""

from __future__ import annotations

import json

import pytest

from footnote.live.analysis import Analysis
from footnote.live.match import Match, load_match
from footnote.live.state import RunState
from footnote.tools import server as tools
from footnote.tools.scope import Scope, Scopes

RUN = "r1"


@pytest.fixture(scope="module")
def showcase() -> Match:
    return load_match()


@pytest.fixture(scope="module")
def analysis(showcase: Match) -> Analysis:
    return Analysis.load(showcase)


class MemorySource:
    """Insight rows from folding the showcase feed, and the feed itself, as the store would give them;
    for a replay that jumped in after `backfill_seq`, if one is given."""

    def __init__(self, showcase: Match, analysis: Analysis, backfill_seq: int = 0) -> None:
        state = RunState.rebuild(
            showcase.match_id, showcase.home_id, showcase.away_id, showcase.feed, analysis, backfill_seq
        )
        assert state.book is not None
        self.rows = {i.insight_id: i.record() for i in state.book.insights.values()}
        self.messages = showcase.feed
        self.reads = 0

    async def insight(self, run_id: str, insight_id: str) -> dict | None:
        return self.rows.get(insight_id) if run_id == RUN else None

    async def feed(self, run_id: str, upto_seq: int) -> list[dict]:
        self.reads += 1
        return [m for m in self.messages if m["seq"] <= upto_seq]


@pytest.fixture(scope="module")
def source(showcase: Match, analysis: Analysis) -> MemorySource:
    return MemorySource(showcase, analysis)


async def _scope(source: MemorySource, showcase: Match, analysis: Analysis, insight_id: str) -> Scope:
    return await Scopes(source, showcase, analysis).get(RUN, insight_id)


async def test_the_tools_see_the_match_as_of_the_moment(
    source: MemorySource, showcase: Match, analysis: Analysis
) -> None:
    scope = await _scope(source, showcase, analysis, "goal-e0391")
    assert scope.state.seq == 392
    events = json.loads(tools.events(scope, ["e0391", "e1029"]))
    assert events["events"] == ["e0391"] and events["missing"] == ["e1029"]  # the 52nd-minute goal hasn't happened
    stats = json.loads(tools.match_stats(scope))["facts"]
    assert stats["score.line"]["value"].endswith("Kingsferry") and stats["score.KIN"]["value"] == 1
    assert stats["teams.SAL.possession"]["value"] > 0.6  # Saltmarsh had the ball
    state = json.loads(tools.match_state(scope, 10))["facts"]
    assert state["state.now"]["display"] == "Kingsferry on the break"
    assert state["state.last.SAL.control"]["value"] > state["state.last.KIN.control"]["value"]


async def test_a_moment_carries_its_facts_and_the_template(
    source: MemorySource, showcase: Match, analysis: Analysis
) -> None:
    scope = await _scope(source, showcase, analysis, "goal-e0391")
    moment = json.loads(tools.moment(scope))
    assert moment["topic"] == "goal" and moment["minute"] == "23'"
    assert moment["facts"]["moment.scorer"]["display"] == "Femi Adeyani"
    assert moment["template"]["headline"] == "{moment.scorer} scores"
    assert "e0391" in moment["events"]


async def test_players_and_events_carry_their_figures(
    source: MemorySource, showcase: Match, analysis: Analysis
) -> None:
    scope = await _scope(source, showcase, analysis, "goal-e1029")  # Varlan's 52nd-minute goal
    varlan = json.loads(tools.player(scope, "sal-10"))["facts"]
    assert varlan["player.sal-10.name"]["value"] == "Teo Varlan"
    assert varlan["player.sal-10.goals"]["display"] == "1 goal"
    assert scope.state.insight is not None
    line = scope.state.insight.player_line("sal-10")
    assert varlan["player.sal-10.passes"]["value"] == line["passes"] > 0
    assert varlan["player.sal-10.pass_difficulty"]["value"] == line["difficulty"]
    assert "player.sal-10.top_speed" in varlan
    shot = json.loads(tools.events(scope, ["e1028"]))["facts"]
    assert shot["event.e1028.speed"]["value"] == 105.7 and shot["event.e1028.type"]["value"] == "shot"
    assert json.loads(tools.player(scope, "nobody"))["error"].startswith("no player")


async def test_the_offside_goal_doesnt_count_and_corrections_apply(
    source: MemorySource, showcase: Match, analysis: Analysis
) -> None:
    dellow = json.loads(tools.player(await _scope(source, showcase, analysis, "var-e0534"), "sal-09"))["facts"]
    assert dellow["player.sal-09.goals"]["value"] == 0  # VAR ruled it out
    scope = await _scope(source, showcase, analysis, "correction-e1586-v2")
    goal = json.loads(tools.events(scope, ["e1586"]))["facts"]
    assert goal["event.e1586.player"]["value"] == "Femi Adeyani"  # as corrected, not the own goal
    assert json.loads(tools.player(scope, "kin-07"))["facts"]["player.kin-07.goals"]["value"] == 2


async def test_recent_events_and_lineups(source: MemorySource, showcase: Match, analysis: Analysis) -> None:
    scope = await _scope(source, showcase, analysis, "goal-e1586")
    recent = json.loads(tools.recent_events(scope, 5))
    assert recent["events"][-1] == "e1586" and all(m["seq"] <= 1620 for m in scope.feed)
    squads = json.loads(tools.lineups(scope))
    kin = next(c for c in squads["clubs"] if c["club"] == "Kingsferry")
    status = {p["player_id"]: p["status"] for p in kin["players"]}
    assert status["kin-03"] == "substituted off" and status["kin-17"] == "on the pitch"


async def test_the_story_tells_the_match_as_it_stands(
    source: MemorySource, showcase: Match, analysis: Analysis
) -> None:
    told = json.loads(tools.story(await _scope(source, showcase, analysis, "ft")))
    moments, facts = told["moments"], told["facts"]
    goals = [m for m in moments if m["topic"] in ("goal", "own_goal")]
    # Dellow's 31st-minute goal was ruled out: the VAR decision tells it. The 81st-minute goal is
    # Adeyani's, as corrected at 84', and says it was corrected.
    assert [g["minute"] for g in goals] == ["23'", "52'", "81'"]
    scorers = [facts[f"story.{g['moment']}.scorer"]["display"] for g in goals]
    assert scorers == ["Femi Adeyani", "Teo Varlan", "Femi Adeyani"]
    assert goals[2]["corrected"].startswith("The provider amended the goal")
    decision = next(m for m in moments if m["topic"] == "var_decision")
    assert decision["minute"] == "33'" and "e0532" in decision["events"]
    assert {m["topic"] for m in moments} >= {"control", "pressure", "chaos", "correction"}
    # Each moment's facts have keys of their own, and its wording uses them.
    n = goals[0]["moment"]
    assert goals[0]["headline"] == f"{{story.{n}.scorer}} scores"
    assert "(goal at 23')" in facts[f"story.{n}.scorer"]["about"]
    assert set(told["events"]) >= {e for m in moments for e in m["events"]}
    assert [m["moment"] for m in moments] == list(range(1, len(moments) + 1))


async def test_a_catch_up_story_ends_where_the_viewer_joins(showcase: Match, analysis: Analysis) -> None:
    source = MemorySource(showcase, analysis, backfill_seq=1137)  # a replay from 60'
    scope = await _scope(source, showcase, analysis, "catchup")
    assert scope.state.seq == 1137
    told = json.loads(tools.story(scope))
    assert told["moments"][-1]["minute"] == "57'"
    assert [m["minute"] for m in told["moments"] if m["topic"] == "goal"] == ["23'", "52'"]
    moment = json.loads(tools.moment(scope))
    assert moment["topic"] == "catch_up" and moment["template"]["headline"] == "What you missed, up to {recap.to}"


async def test_scopes_fold_once_per_moment(source: MemorySource, showcase: Match, analysis: Analysis) -> None:
    scopes = Scopes(source, showcase, analysis)
    before = source.reads
    a = await scopes.get(RUN, "goal-e0391")
    b = await scopes.get(RUN, "goal-e0391")
    assert a.state is b.state and source.reads == before + 1
    # The restated goal and its correction notice come from the same message: one fold for both.
    goal = await scopes.get(RUN, "goal-e1586")
    notice = await scopes.get(RUN, "correction-e1586-v2")
    assert goal.state is notice.state and source.reads == before + 2
    with pytest.raises(LookupError):
        await scopes.get(RUN, "no-such-insight")
