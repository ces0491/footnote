"""The agents' evaluations: each evaluator on cards made for it, and the recorded live run replayed
through today's writer workflow, checks and evaluators (docs/evaluations.md)."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from footnote.agents.prompts import PROMPT_VERSION
from footnote.agents.versions import VERSIONS, fingerprint
from footnote.agents.worker import Settings
from footnote.evals.cases import JUMPS, Case, cases
from footnote.evals.groundedness import openai_endpoint, verdict
from footnote.evals.judges import (
    Seen,
    Verdict,
    adds_to_the_template,
    claims_hold,
    names_the_subject,
    one_line_per_figure,
)
from footnote.evals.report import write_report
from footnote.evals.run import JUDGE_TRIES, PASSING_SHARE, Result, judge_groundedness, passing, replay, stale
from footnote.insights import facts as F
from footnote.insights.draft import Card, Draft, Sentence, render
from footnote.insights.facts import Facts
from footnote.live.analysis import Analysis
from footnote.live.match import Match, load_match

ROOT = Path(__file__).resolve().parents[1]
RECORDING = ROOT / "data" / "evals" / "drafts.json"
REPORT = ROOT / "docs" / "evaluations.md"


@pytest.fixture(scope="module")
def showcase() -> Match:
    return load_match()


@pytest.fixture(scope="module")
def analysis(showcase: Match) -> Analysis:
    return Analysis.load(showcase)


GOAL: Facts = {
    "moment.scorer": F.text("Femi Adeyani", "who put the ball in the net", ("e0391",)),
    "moment.club": F.text("Kingsferry", "the club the goal counts for"),
    "moment.minute": F.minute(23, None, "minute of the goal", ("e0391",)),
    "moment.situation": F.text("take the lead", "what the goal does to the score"),
    "moment.shot_speed": F.speed(89.1, "speed of the shot", ("e0390",)),
    "moment.shot_distance": F.metres(21.0, "distance of the shot from goal", ("e0390",)),
    "moment.score_line": F.text("Saltmarsh 0-1 Kingsferry", "the score after the goal", ("e0391",)),
    "moment.other_club": F.text("Saltmarsh", "the other club"),
}


def _card(
    casual: str, analyst: str = "The shot left the boot at {moment.shot_speed}.", headline: str = "Goal"
) -> Draft:
    return Draft(
        headline=headline,
        casual=[Sentence(text=casual, events=["e0391"])],
        analyst=[Sentence(text=analyst, events=[])],
    )


def _seen(facts: Facts = GOAL, topic: str = "goal", corrected: bool = False) -> Seen:
    return Seen(topic=topic, moment=facts, facts=facts, corrected=corrected)


def _judge(judge: Callable[[Seen, Card, Draft], Verdict], draft: Draft, seen: Seen | None = None) -> Verdict:
    seen = seen or _seen()
    return judge(seen, render(draft, seen.facts), draft)


def test_a_card_names_who_it_is_about() -> None:
    assert _judge(names_the_subject, _card("{moment.club} take the lead through {moment.scorer}.")).passed
    missing = _judge(names_the_subject, _card("{moment.club} take the lead on the break."))
    assert not missing.passed and missing.note == "never names Femi Adeyani"
    goals = F.text("Femi Adeyani (Kingsferry) 23', Teo Varlan (Saltmarsh) 52'", "the goals")
    recap = {**GOAL, "recap.goals": goals}
    told = _judge(names_the_subject, _card("Adeyani struck before Varlan levelled."), _seen(recap, "half_time"))
    untold = _judge(names_the_subject, _card("Adeyani struck before the break."), _seen(recap, "half_time"))
    assert told.passed and not untold.passed and untold.note == "leaves out Varlan"


def test_a_claim_in_words_needs_a_fact_behind_it() -> None:
    assert not _judge(claims_hold, _card("{moment.scorer} scores against the run of play.")).passed
    assert not _judge(claims_hold, _card("{moment.scorer} equalises for {moment.club}.")).passed
    assert not _judge(claims_hold, _card("{moment.scorer} scores after a goal was ruled out.")).passed
    against = {**GOAL, "moment.run_of_play": F.text("against the run of play", "the state model's view")}
    assert _judge(claims_hold, _card("{moment.scorer} scores against the run of play."), _seen(against)).passed
    # Denied, it isn't a claim; and a restated card may say it was corrected.
    assert _judge(claims_hold, _card("{moment.other_club} could not find an equaliser.")).passed
    assert _judge(claims_hold, _card("{moment.scorer} is credited after a correction."), _seen(corrected=True)).passed


def test_a_penalty_given_needs_a_decision_that_gave_one() -> None:
    checked = {
        "moment.subject": F.text("Uche Asatoye", "the player the check is about", ("e1456",)),
        "moment.check": F.text("penalty", "what VAR checked for"),
        "moment.incident": F.text("handball", "the incident"),
        "moment.decision": F.text("no_penalty", "the decision"),
    }
    seen = _seen(checked, "var_decision")
    analyst = "The check was about {moment.incident}."
    gives = _judge(claims_hold, _card("VAR gives a penalty for handball by {moment.subject}.", analyst), seen)
    assert not gives.passed and "a penalty given" in gives.note
    found = _card("VAR checked {moment.subject} for a penalty and found none.", analyst)
    assert _judge(claims_hold, found, seen).passed
    given = _seen({**checked, "moment.decision": F.text("penalty", "the decision")}, "var_decision")
    assert _judge(claims_hold, _card("VAR gives a penalty for handball by {moment.subject}.", analyst), given).passed


def test_the_recording_goes_stale_with_any_change_to_what_the_writers_see() -> None:
    recording = {"versions": dict(VERSIONS), "reasoning_effort": Settings.reasoning_effort}
    assert stale(recording) == []
    # Each version carries a fingerprint of its code, so an edit that forgets the version still counts.
    assert VERSIONS["prompt"].startswith(PROMPT_VERSION + "+")
    older = {**recording, "versions": {**VERSIONS, "prompt": PROMPT_VERSION}}
    assert stale(older) == [f"prompt {PROMPT_VERSION} -> {VERSIONS['prompt']}"]
    assert stale({**recording, "reasoning_effort": "medium"}) == ["reasoning effort medium -> low"]
    # The same code gives the same fingerprint whatever line endings the checkout has.
    assert fingerprint(rendered=("a\r\nb",)) == fingerprint(rendered=("a\nb",)) != fingerprint(rendered=("a\nc",))


def test_a_card_must_be_more_than_the_template_reworded() -> None:
    template = "{moment.score_line}: {moment.scorer} scores at {moment.minute}."
    copied = _judge(adds_to_the_template, _card(template))
    assert not copied.passed and "of its words are the template's" in copied.note
    own = _judge(adds_to_the_template, _card("{moment.club} break away to take the lead through {moment.scorer}."))
    assert own.passed


def test_each_line_gets_figures_of_its_own() -> None:
    twice = _judge(one_line_per_figure, _card("It left the boot at {moment.shot_speed}."))
    assert not twice.passed and twice.note == "moment.shot_speed in both lines"
    # The minute places the moment, so it may be in both.
    minute = _card("{moment.scorer} scores at {moment.minute}.", "The shot at {moment.minute} hit {moment.shot_speed}.")
    assert _judge(one_line_per_figure, minute).passed


def test_the_judge_reaches_the_foundry_accounts_openai_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FOUNDRY_OPENAI_ENDPOINT", raising=False)
    project = "https://ai-footnote-abc123.services.ai.azure.com/api/projects/footnote"
    assert openai_endpoint(project) == "https://ai-footnote-abc123.openai.azure.com/"
    assert verdict(None) is None
    failed = verdict({"score": 2.0, "passed": False, "reason": "says the only shot of the match"})
    assert failed is not None and not failed.passed and failed.note.startswith("scored 2.0")


class _Judge:
    """A judge whose first `unreadable` replies can't be parsed, as the evaluator's model sometimes sends."""

    def __init__(self, unreadable: int) -> None:
        self.unreadable, self.asked = unreadable, 0

    async def judge(self, card: Card, facts: Facts, reason: str) -> dict:
        self.asked += 1
        if self.asked <= self.unreadable:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return {"score": 4.0, "passed": True, "reason": "supported by the facts"}


async def test_a_judge_reply_that_cant_be_read_is_asked_again() -> None:
    case = Case("goal-e0391/v1", {"insight_id": "goal-e0391", "reason": "Goal"})
    card = render(_card("{moment.scorer} scores."), GOAL)
    late = _Judge(unreadable=JUDGE_TRIES - 1)
    judged = Result(case, "accepted", card=card)
    await judge_groundedness([judged], late)
    assert late.asked == JUDGE_TRIES and judged.passed
    # A judge that never answers is a fail, said as the judge's.
    silent = _Judge(unreadable=JUDGE_TRIES)
    unjudged = Result(case, "accepted", card=card)
    await judge_groundedness([unjudged], silent)
    assert silent.asked == JUDGE_TRIES and not unjudged.passed
    assert unjudged.groundedness is not None and unjudged.groundedness["reason"].startswith("the judge failed")


def test_the_cases_are_every_agent_job_in_a_replay(showcase: Match, analysis: Analysis) -> None:
    keys = [c.key for c in cases(showcase, analysis)]
    # The 81st-minute goal is drafted twice: as the own goal first recorded, and as corrected.
    assert "goal-e1586/v1" in keys and "goal-e1586/v2" in keys
    assert {"ht/v1", "ft/v1"} <= set(keys)
    assert [k for k in keys if k.startswith("catchup@")] == [f"catchup@{m}" for m in JUMPS]
    assert len(keys) == len(set(keys))


@pytest.fixture(scope="module")
def replayed(showcase: Match, analysis: Analysis) -> tuple[dict, list[Case], list[Result]]:
    """The recording, the cases and the recorded run replayed once through today's writer workflow,
    checks and evaluators, on the loop the CLI uses."""
    recording = json.loads(RECORDING.read_text(encoding="utf-8"))
    all_cases = cases(showcase, analysis)
    factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    with asyncio.Runner(loop_factory=factory) as runner:
        results = runner.run(replay(showcase, analysis, all_cases, recording))
    return recording, all_cases, results


def test_the_recorded_run_passes_todays_checks_and_evaluations(
    replayed: tuple[dict, list[Case], list[Result]],
) -> None:
    """The model's recorded output, replayed through today's writer workflow, checks and evaluators.

    A change to the checks, the facts or the tools that a recorded draft no longer passes fails here;
    so does a change to the agents' instructions, tools or workflow (their versions carry a
    fingerprint of the code) until the evaluations are run and recorded again:
    `uv run --group evals python -m footnote.evals live --record --report`.
    """
    recording, all_cases, results = replayed
    assert stale(recording) == [], "record the evaluations again"
    assert {c.key for c in all_cases} == set(recording["cases"]), "record the evaluations again"
    for result in results:
        live = recording["cases"][result.case.key]["outcome"]
        if live == "accepted":
            assert result.outcome == "accepted", (result.case.key, result.problems)
            assert any(v.evaluator == "grounded" for v in result.verdicts), result.case.key
    assert passing(results) >= PASSING_SHARE, [(r.case.key, [v for v in r.verdicts if not v.passed]) for r in results]


def test_the_evaluations_page_is_the_recordings_replay(
    replayed: tuple[dict, list[Case], list[Result]], tmp_path: Path
) -> None:
    """docs/evaluations.md is what `python -m footnote.evals replay --report` writes from the recording,
    so a change to the checks shows on the page as soon as it lands."""
    recording, _, results = replayed
    written = tmp_path / "evaluations.md"
    write_report(written, results, recording)
    committed = REPORT.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert written.read_text(encoding="utf-8").replace("\r\n", "\n") == committed, (
        "write it again: uv run python -m footnote.evals replay --report"
    )
