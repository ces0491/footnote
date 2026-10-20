"""Insights on the showcase match: what is found and how it ranks, what VAR and corrections do to
it, and the checks every draft passes (templates' and agents' alike)."""

from __future__ import annotations

import pytest

from footnote.insights.book import Insight
from footnote.insights.draft import Draft, Sentence, check, render
from footnote.insights.facts import NBSP, Fact, duration, minute, share, speed
from footnote.live.analysis import Analysis
from footnote.live.match import Match, load_match
from footnote.live.state import RunState


@pytest.fixture(scope="module")
def showcase() -> Match:
    return load_match()


@pytest.fixture(scope="module")
def analysis(showcase: Match) -> Analysis:
    return Analysis.load(showcase)


@pytest.fixture(scope="module")
def final(showcase: Match, analysis: Analysis) -> RunState:
    return RunState.rebuild(showcase.match_id, showcase.home_id, showcase.away_id, showcase.feed, analysis)


def _insights(state: RunState) -> dict[str, Insight]:
    assert state.book is not None
    return state.book.insights


def _as_of(showcase: Match, analysis: Analysis, seq: int) -> RunState:
    return RunState.rebuild(showcase.match_id, showcase.home_id, showcase.away_id, showcase.feed[:seq], analysis)


def test_every_template_passes_the_checks(showcase: Match, final: RunState) -> None:
    events = {m["event_id"] for m in showcase.feed}
    insights = _insights(final)
    assert len(insights) > 20
    for insight in insights.values():
        assert check(insight.template, insight.facts, events) == [], insight.insight_id
        assert set(insight.evidence) <= events


def test_the_first_goal_ranks_top_as_against_the_run_of_play(showcase: Match, analysis: Analysis) -> None:
    goal_seq = next(m["seq"] for m in showcase.feed if m["type"] == "goal")
    insights = _insights(_as_of(showcase, analysis, goal_seq))
    goal = insights["goal-e0391"]
    assert goal.rank == max(i.rank for i in insights.values())
    assert goal.reason.startswith("Goal: against the run of play: Saltmarsh were on top for")
    assert goal.facts["moment.run_of_play"].value == "against the run of play"
    assert goal.facts["moment.other_on_top"].value >= 0.45 >= 0.25 >= goal.facts["moment.club_on_top"].value
    assert goal.agent and goal.live
    assert "keypass-e0387" in insights  # the pass that set it up, with its difficulty


def test_var_rules_out_the_31st_minute_goal(final: RunState) -> None:
    insights = _insights(final)
    goal, decision = insights["goal-e0532"], insights["var-e0534"]
    assert goal.flag is not None and goal.flag["reason"] == "Ruled out by VAR" and goal.flag["event_id"] == "e0534"
    assert goal.until == {"period": 1, "t": 1931.7}  # off the shortlist from the decision
    assert decision.topic == "var_decision" and {"e0532", "e0529"} <= set(decision.evidence)
    assert decision.card().casual.startswith("Marco Dellow was offside when Teo Varlan played the pass")
    assert decision.flag is None
    # The pass that set the goal up cites it, so it goes with it.
    key_pass = insights["keypass-e0529"]
    assert key_pass.flag is not None and key_pass.flag["event_id"] == "e0534"
    assert key_pass.until == {"period": 1, "t": 1931.7}
    # "VAR is checking" is over once the decision is in; it is no less true, so it isn't flagged.
    started = insights["var-e0533"]
    assert started.flag is None and started.until == {"period": 1, "t": 1931.7}


def _current(insights: dict[str, Insight], period: int, t: float) -> list[Insight]:
    """What the producer's shortlist may offer at a moment (frontend/src/lib/live/shortlist.ts)."""
    now = (period, t)
    return [
        i
        for i in insights.values()
        if i.live
        and i.kind != "correction"
        and i.flag is None
        and (i.at["period"], i.at["t"]) <= now <= (i.until["period"], i.until["t"])
    ]


@pytest.mark.parametrize("after", [1, 30, 90])
def test_after_a_goal_is_ruled_out_nothing_on_offer_says_otherwise(
    showcase: Match, analysis: Analysis, after: int
) -> None:
    decision = next(m for m in showcase.feed if m["event_id"] == "e0534")
    insights = _insights(_as_of(showcase, analysis, decision["seq"]))
    offered = _current(insights, 1, decision["t"] + after)
    assert [i.insight_id for i in offered if "e0532" in i.evidence] == ["var-e0534"]


def test_a_check_that_upholds_the_call_ends_its_started_card(final: RunState) -> None:
    started, decision = _insights(final)["var-e1455"], _insights(final)["var-e1456"]
    assert decision.facts["moment.decision"].value == "no_penalty"
    assert started.flag is None and started.until == {"period": 2, "t": 1773.71}


def test_every_card_links_to_events_but_tags_from_the_tracking(showcase: Match, final: RunState) -> None:
    for insight in _insights(final).values():
        evidence = insight.card().evidence
        if insight.kind == "player_tag":
            assert evidence == (), insight.insight_id  # sprints and distances rest on the tracking
        else:
            assert evidence and set(evidence) <= set(insight.evidence), insight.insight_id
    # A spell's card cites play from the spell itself.
    by_id = {m["event_id"]: m for m in showcase.feed}
    segments = [i for i in _insights(final).values() if i.kind == "segment"]
    assert segments
    for insight in segments:
        period, start = (int(part) for part in insight.insight_id.split("-")[-2:])
        end = start + insight.facts["segment.window"].value
        assert all(by_id[e]["period"] == period and start <= by_id[e]["t"] < end for e in insight.card().evidence), (
            insight.insight_id
        )


def test_the_amended_goal_is_restated_and_a_correction_cites_it(final: RunState) -> None:
    insights = _insights(final)
    goal = insights["goal-e1586"]
    assert goal.topic == "goal" and goal.facts_version == 2 and goal.seq == 1620
    assert goal.facts["moment.scorer"].display == "Femi Adeyani"
    assert goal.flag is not None and goal.flag["event_id"] == "e1586" and goal.flag["version"] == 2
    correction = insights["correction-e1586-v2"]
    assert correction.kind == "correction" and correction.corrects == "goal-e1586" and correction.rank == 0.95
    assert "Jory Penhallow (own goal)" in correction.card().casual


def test_insights_the_backfill_passed_are_history(showcase: Match, analysis: Analysis) -> None:
    backfill_seq = 1500
    state = RunState(showcase.match_id, showcase.home_id, showcase.away_id, analysis, backfill_seq)
    for m in showcase.feed:
        state.apply(m)
    insights = _insights(state)
    assert not insights["goal-e0391"].live and not insights["goal-e0391"].agent
    assert insights["correction-e1586-v2"].live and insights["correction-e1586-v2"].agent
    # The 81' goal came after the backfill: live, and drafted again once the correction restates it.
    assert insights["goal-e1586"].live and insights["goal-e1586"].agent


def test_a_rebuilt_run_finds_the_same_insights(showcase: Match, analysis: Analysis, final: RunState) -> None:
    incremental = RunState(showcase.match_id, showcase.home_id, showcase.away_id, analysis)
    changes = []
    for m in showcase.feed:
        incremental.apply(m)
        changes += incremental.insight_changes()
    assert [i.record() for i in _insights(incremental).values()] == [i.record() for i in _insights(final).values()]
    assert {c.what for c in changes} == {"new", "flagged", "restated", "ended"}


def test_segments_come_from_the_state_model(final: RunState) -> None:
    segments = [i for i in _insights(final).values() if i.kind == "segment"]
    # The story's 38-45' beat: Saltmarsh pinning Kingsferry back (docs/experience.md).
    pressure = [i for i in segments if i.topic == "pressure" and i.at["period"] == 1 and 38 <= i.at["minute"] <= 45]
    assert any(i.facts["segment.club"].value == "Saltmarsh" for i in pressure)
    chaos = [i for i in segments if i.topic == "chaos"]
    assert chaos and all(i.at["period"] == 2 and 63 <= i.at["minute"] <= 70 for i in chaos)
    assert all(i.hold == "stoppage" for i in segments)


FACTS = {
    "teams.SAL.possession": share(0.712, "share of passes"),
    "teams.SAL.name": Fact("Saltmarsh", "Saltmarsh", "club"),
    "player.kin-07.name": Fact("Femi Adeyani", "Femi Adeyani", "player", ("e0391",)),
    "player.sal-10.name": Fact("Teo Varlan", "Teo Varlan", "player"),
    "moment.minute": minute(23, None, "minute", ("e0391",)),
    "moment.speed": speed(33.84, "top speed"),
}
EVENTS = frozenset({"e0391", "e0390"})


def _draft(casual: str, analyst: str = "{teams.SAL.name} have {teams.SAL.possession} of the ball.", **kw) -> Draft:
    return Draft(
        headline=kw.get("headline", "{player.kin-07.name} scores"),
        casual=[Sentence(text=casual, events=kw.get("events", ["e0391"]))],
        analyst=[Sentence(text=analyst, events=[])],
    )


def test_a_clean_draft_passes_and_renders_with_the_figures_from_code() -> None:
    draft = _draft("{player.kin-07.name} scores at {moment.minute} and Saltmarsh are behind.")
    assert check(draft, FACTS, EVENTS) == []
    card = render(draft, FACTS)
    assert card.casual == "Femi Adeyani scores at 23' and Saltmarsh are behind."
    assert card.analyst == "Saltmarsh have 71% of the ball."
    assert card.plain == "Femi Adeyani scores. " + card.casual
    assert card.evidence == ("e0391",) and "teams.SAL.possession" in card.facts


@pytest.mark.parametrize(
    ("casual", "problem"),
    [
        ("Adeyani scores at 23 minutes.", "typed as digits"),
        ("Saltmarsh have had seventy per cent of the ball.", "written as a word"),
        ("Saltmarsh have had most of the ball, per cent wise.", "'per cent' written out"),
        ("{teams.KIN.possession} for the visitors.", "unknown fact"),
        ("A goal for Riverton against Saltmarsh.", "'Riverton' isn't a name"),
        ("{player.kin-07.name} scores! Great.", "exclamation"),
        ("The odds on {player.kin-07.name} scoring have shortened.", "betting language"),
        ("A {brace} too far.", "a brace that isn't a whole placeholder"),
        # Figures in words: scores, ordinals, football's counts, shares.
        ("{player.kin-07.name} puts Saltmarsh one-nil down.", "the number 'one' written as a word"),
        ("It is {player.kin-07.name}'s first goal of the season.", "the number 'first' written as a word"),
        ("{player.kin-07.name} completes a hat-trick.", "the number 'hat-trick' written as a word"),
        ("{player.kin-07.name} scores in the twentieth minute.", "the number 'twentieth' written as a word"),
        ("{player.kin-07.name} has a brace.", "the number 'brace' written as a word"),
        ("Saltmarsh have had half the ball.", "a share written in words ('half the')"),
        # Names: after a colon or a bracket, in a second sentence, in other alphabets, or two joined.
        ("{player.kin-07.name} scores: Haaland would be proud.", "'Haaland' isn't a name"),
        ("{player.kin-07.name} scores (Haaland would be proud).", "'Haaland' isn't a name"),
        ("{player.kin-07.name} scores. Riverton are top.", "more than one sentence"),
        ("{player.kin-07.name} scores as " + chr(0xD8) + "degaard watches.", "degaard' isn't a name"),
        ("Teo Adeyani scores for Saltmarsh.", "'Teo Adeyani' isn't a name as any one fact gives it"),
    ],
)
def test_the_checks_catch_figures_names_and_tone(casual: str, problem: str) -> None:
    problems = check(_draft(casual), FACTS, EVENTS)
    assert any(problem in p for p in problems), problems


@pytest.mark.parametrize(
    "casual",
    [
        "{player.kin-07.name} scores early in the second half.",
        "No one picks up {player.kin-07.name} in the final third.",
        "It is one of the better moves by {teams.SAL.name} today.",
        "Saltmarsh's Teo Varlan finds Adeyani with a first-time pass.",
        "The goal comes at {moment.minute}, against the run of play.",
    ],
)
def test_the_checks_let_ordinary_football_words_and_names_through(casual: str) -> None:
    assert check(_draft(casual), FACTS, EVENTS) == []


def test_a_card_must_link_to_an_event_when_its_facts_rest_on_some() -> None:
    draft = _draft("{teams.SAL.name} have {teams.SAL.possession} of the ball.", events=[], headline="Saltmarsh on top")
    assert any("links to no event" in p for p in check(draft, FACTS, EVENTS))
    tracking_only = {"moment.speed": FACTS["moment.speed"], "teams.SAL.name": FACTS["teams.SAL.name"]}
    tag = Draft(
        headline="Top speed",
        casual=[Sentence(text="{teams.SAL.name} hit {moment.speed}.", events=[])],
        analyst=[Sentence(text="From the tracking.", events=[])],
    )
    assert not any("links to no event" in p for p in check(tag, tracking_only, EVENTS))


def test_every_sentence_must_rest_on_an_event_or_a_fact_and_cite_only_what_it_was_shown() -> None:
    assert any("rests on nothing" in p for p in check(_draft("A fine goal.", events=[]), FACTS, EVENTS))
    unseen = check(_draft("{player.kin-07.name} scores.", events=["e9999"]), FACTS, EVENTS)
    assert any("e9999" in p and "no tool returned" in p for p in unseen)


def test_length_limits_apply_to_the_filled_in_text() -> None:
    long_casual = "{player.kin-07.name} scores and " + "keeps going and " * 20 + "stops."
    assert any("characters once filled in" in p for p in check(_draft(long_casual), FACTS, EVENTS))
    too_many = Draft(
        headline="Goal",
        casual=[Sentence(text="{player.kin-07.name} scores.", events=["e0391"])] * 3,
        analyst=[Sentence(text="At {moment.minute}.", events=[])],
    )
    assert any("casual: 3 sentences" in p for p in check(too_many, FACTS, EVENTS))


def test_facts_show_figures_the_way_cards_print_them() -> None:
    assert share(0.712, "").display == "71%"
    assert speed(33.84, "").display == f"33.8{NBSP}km/h"
    assert minute(45, 2, "").display == "45+2'"
    assert duration(92, "").display == "92 seconds" and duration(600, "").display == "10 minutes"
