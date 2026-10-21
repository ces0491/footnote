"""Evaluations of an agent's card beyond the checks it passed.

The checks (footnote.insights.draft) make sure every figure and name came from the facts. What they
can't see is whether the card is any good: whether it names who the moment is about (ESPN's recap of
Alex Morgan's final match that didn't mention her, docs/audience.md), whether a claim it makes in
words is one the facts support ("against the run of play", "an own goal", "ruled out"), whether it
says more than the template already did, and whether it spends both lines on one figure. Each
evaluator here answers one of those from the card, the draft and the facts, in code, and each is a
rough test: none of them can tell whose a claim is, so a card that gives the right words to the
wrong player or moment passes all four. Reading the cards stays part of a review.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from footnote.insights.draft import Card, Draft, placeholders, render
from footnote.insights.facts import Fact, Facts, facts_from_json
from footnote.insights.templates import template


@dataclass(frozen=True)
class Verdict:
    evaluator: str
    passed: bool
    note: str = ""


@dataclass(frozen=True)
class Seen:
    """What the evaluators know about a card: its moment, and what its writer was given."""

    topic: str
    moment: Facts  # the insight's own facts
    facts: Facts  # every fact the writer's tools returned
    corrected: bool  # a correction restated the moment


# Whose name a card about each topic should carry: the fact that holds it.
SUBJECT = {
    "goal": "moment.scorer",
    "own_goal": "moment.scorer",
    "var_decision": "moment.subject",
    "red_card": "moment.player",
    "penalty": "moment.club",
    "correction": "correction.after",
    "pressure": "segment.club",
    "control": "segment.club",
}
RECAPS = frozenset({"half_time", "full_time", "catch_up"})
# A recap's goals fact, as moments.py writes it: "Femi Adeyani (Kingsferry) 23', Teo Varlan (...) 52'".
_SCORER = re.compile(r"(?:^|, )([^(,]+?) \(")


def _surname(name: str) -> str:
    return name.split()[-1]


def names_the_subject(seen: Seen, card: Card, draft: Draft) -> Verdict:
    """The headline or the casual line has the surname of who the moment is about; a recap's, of
    every scorer. It looks for the name, not at what the card says about them."""
    text = f"{card.headline} {card.casual}"
    if seen.topic in RECAPS:
        goals = seen.moment.get("recap.goals")
        scorers = sorted({_surname(n) for n in _SCORER.findall(goals.display)}) if goals else []
        missing = [s for s in scorers if s not in text]
        return Verdict("names the subject", not missing, f"leaves out {', '.join(missing)}" if missing else "")
    key = SUBJECT.get(seen.topic)
    if key is None or key not in seen.moment:
        return Verdict("names the subject", True, "no single subject")
    name = seen.moment[key].display
    ok = _surname(name) in text
    return Verdict("names the subject", ok, "" if ok else f"never names {name}")


def _any(facts: Facts, test: Callable[[str, Fact], bool]) -> bool:
    """Whether any fact passes `test`, given the last part of its key and the fact."""
    return any(test(key.rsplit(".", 1)[-1], fact) for key, fact in facts.items())


def _shows(facts: Facts, text: str) -> bool:
    return _any(facts, lambda k, f: text in f.display.lower())


def _counted(facts: Facts, name: str) -> bool:
    return _any(facts, lambda k, f: k == name and isinstance(f.value, int) and f.value > 0)


# A claim made in words, and what must hold for the card to make it.
CLAIMS: list[tuple[str, re.Pattern[str], Callable[[Seen], bool]]] = [
    (
        "against the run of play",
        re.compile(r"against the run of play", re.I),
        lambda s: _any(s.facts, lambda k, f: k == "run_of_play"),
    ),
    (
        "an equaliser",
        re.compile(r"\bequalis|\blevel(?:s|led|ling)?\b|\ball square\b", re.I),
        lambda s: _any(s.facts, lambda k, f: k == "situation" and f.value == "equalise"),
    ),
    (
        "an own goal",
        re.compile(r"\bown goal\b", re.I),
        lambda s: s.topic == "own_goal" or _shows(s.facts, "own goal"),
    ),
    ("offside", re.compile(r"\boffside\b", re.I), lambda s: _any(s.facts, lambda k, f: f.value == "offside")),
    ("handball", re.compile(r"\bhandball\b", re.I), lambda s: _any(s.facts, lambda k, f: f.value == "handball")),
    (
        "a penalty given",
        re.compile(
            r"\b(?:gives?|given|awards?|awarded)\b[^.;:]{0,30}\bpenalt|\bpenalt\w*\s+(?:is\s+|was\s+)?(?:given|awarded)\b",
            re.I,
        ),
        lambda s: s.topic == "penalty" or _any(s.facts, lambda k, f: k == "decision" and f.value == "penalty"),
    ),
    (
        "a penalty",
        re.compile(r"\bpenalt", re.I),
        lambda s: (
            s.topic == "penalty" or _any(s.facts, lambda k, f: k in ("check", "decision") and f.value == "penalty")
        ),
    ),
    (
        "a goal ruled out",
        re.compile(r"\bruled out\b|\bdisallow|\bchalked off\b", re.I),
        lambda s: _any(s.facts, lambda k, f: k == "decision" and f.value == "no_goal"),
    ),
    (
        "a sending-off",
        re.compile(r"\bred card\b|\bsent off\b|\bdown to\b", re.I),
        lambda s: s.topic == "red_card" or _counted(s.facts, "red_cards"),
    ),
    (
        "a correction",
        re.compile(r"\bcorrect(?:ed|ion)\b|\bamend|\bre-?credited\b", re.I),
        lambda s: s.corrected or _any(s.facts, lambda k, f: k in ("after", "before")),
    ),
]


# A claim denied, or only supposed, a few words before it isn't made: "could not find an
# equaliser", "thought he had levelled it".
_DENIED = re.compile(
    r"(?:\b(?:not|no|never|without|nor|cannot|failed to|unable to|thought|would have|almost|nearly)\b|n't)"
    r"[^.;:,]{0,40}$",
    re.I,
)


def _claims(pattern: re.Pattern[str], text: str) -> bool:
    return any(not _DENIED.search(text[: m.start()]) for m in pattern.finditer(text))


def claims_hold(seen: Seen, card: Card, draft: Draft) -> Verdict:
    """Each claim from a short list that the card makes in words (against the run of play, an
    equaliser, an own goal, offside, handball, a penalty given or checked for, a goal ruled out, a
    sending-off, a correction) has a fact of its kind among those its writer was given, whoever
    that fact is about."""
    text = f"{card.headline} {card.casual} {card.analyst}"
    unsupported = [name for name, pattern, holds in CLAIMS if _claims(pattern, text) and not holds(seen)]
    note = f"says {', '.join(unsupported)} without a fact for it" if unsupported else ""
    return Verdict("claims hold", not unsupported, note)


# The share of a casual line's words found in the template's casual line above which it is the
# template's line reworded. The writer's checker already refuses the template's line word for word.
MOSTLY_THE_TEMPLATE = 0.8


def _words(text: str) -> set[str]:
    return set(re.findall(r"[^\W\d_]+", text.lower()))


def adds_to_the_template(seen: Seen, card: Card, draft: Draft) -> Verdict:
    """Fewer than four in five of the casual line's words are in the template's casual line, so a
    line that only rewords the template fails; one that keeps most of it and adds a clause passes."""
    plain = render(template(seen.topic, seen.moment), seen.moment)
    own = _words(card.casual)
    shared = len(own & _words(plain.casual)) / len(own) if own else 1.0
    ok = shared < MOSTLY_THE_TEMPLATE
    return Verdict("adds to the template", ok, "" if ok else f"{shared:.0%} of its words are the template's")


def _frames(fact: Fact) -> bool:
    """Whether a figure frames the others rather than saying something itself: a minute ("23'"), or
    the stretch a spell's figures cover ("5 minutes")."""
    return fact.display.endswith("'") or bool(re.match(r"\d+ (?:minutes|seconds)$", fact.display))


def one_line_per_figure(seen: Seen, card: Card, draft: Draft) -> Verdict:
    """No number fact sits in both lines under the same key, so casual and analyst readers each get
    something of their own. A minute or a spell's stretch may be in both: they frame the rest. A
    text fact, such as a score line, isn't counted."""
    casual = {k for s in draft.casual for k in placeholders(s.text)}
    analyst = {k for s in draft.analyst for k in placeholders(s.text)}
    twice = sorted(
        k
        for k in casual & analyst
        if k in seen.facts and isinstance(seen.facts[k].value, int | float) and not _frames(seen.facts[k])
    )
    return Verdict("one line per figure", not twice, f"{', '.join(twice)} in both lines" if twice else "")


EVALUATORS: list[Callable[[Seen, Card, Draft], Verdict]] = [
    names_the_subject,
    claims_hold,
    adds_to_the_template,
    one_line_per_figure,
]


def evaluate(row: dict, draft: Draft, facts: Facts) -> list[Verdict]:
    """Every evaluator's verdict on an accepted draft of the insight in `row`, written from `facts`."""
    flag = row.get("flag")
    seen = Seen(
        topic=str(row["topic"]),
        moment=facts_from_json(row["facts"]),
        facts=facts,
        corrected=flag is not None and flag["seq"] == row["seq"],
    )
    card = render(draft, facts)
    return [judge(seen, card, draft) for judge in EVALUATORS]
