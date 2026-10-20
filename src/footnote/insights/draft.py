"""A card's wording, and the checks it passes before anyone sees it.

A draft is a headline, a line for casual fans and a line for analysts, each sentence listing the
events it rests on. Where a figure goes, the wording has a placeholder naming a fact,
`{teams.SAL.possession}`, never the figure itself: `render` fills placeholders in from the facts, so
the figures on a card are always code's (facts.py). Templates write drafts this way (templates.py),
and so do the agents.

`check` lists what is wrong with a draft, in words an agent can act on:

- every placeholder names a fact the writer was given, and the writer typed no figure of its own:
  no digits, no numbers spelled out, no percentages;
- every capitalised word inside a sentence is a name from the facts, so no player, club or place
  that isn't in the match appears;
- every sentence rests on something: an event it cites, or a fact it uses; and every event it cites
  is one the writer was shown;
- headline and lines fit their space, with no betting language, exclamations, links or emoji.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from footnote.insights.facts import EN_DASH, Facts

PLACEHOLDER = re.compile(r"\{([A-Za-z][A-Za-z0-9_\-]*(?:\.[A-Za-z0-9_\-]+)+)\}")

HEADLINE_CHARS = 60
CASUAL_CHARS = 240
ANALYST_CHARS = 360
CASUAL_SENTENCES = (1, 2)
ANALYST_SENTENCES = (1, 3)

_DIGIT = re.compile(r"\d")
_NUMBER_WORD = re.compile(
    r"\b(two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
    r"seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|"
    r"thousand|million|dozen|twice|thrice)\b",
    re.IGNORECASE,
)
_PERCENT_WORD = re.compile(r"\bper\s?cent\b", re.IGNORECASE)
_BETTING = re.compile(
    r"\b(bet|bets|betting|odds|bookmakers?|bookies?|wagers?|punters?|accumulators?|stake|stakes)\b",
    re.IGNORECASE,
)
_EMOJI = re.compile(f"[{chr(0x1F000)}-{chr(0x1FAFF)}{chr(0x2600)}-{chr(0x27BF)}]")
_LINK = re.compile(r"https?://|www\.", re.IGNORECASE)
_CAPITALISED = re.compile(r"[A-Z][A-Za-z\-']*")
# Where a capitalised word starts a sentence or clause and so needn't be a name.
_SENTENCE_START = re.compile(r"(?:^|[.?:;]\s+|" + EN_DASH + r"\s+|\(\s*)$")
# Capitalised words a card may use that no fact supplies.
ALWAYS_ALLOWED = frozenset({"VAR", "I"})


class Sentence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(description="One sentence. Figures go in as {fact.key} placeholders, never typed.")
    events: list[str] = Field(description="IDs of the events this sentence rests on; may be empty if it uses a fact.")


class Draft(BaseModel):
    """The wording of one card."""

    model_config = ConfigDict(extra="forbid")

    headline: str = Field(description="Up to six words for the lower third.")
    casual: list[Sentence] = Field(description="One or two short sentences for a casual fan: why it matters.")
    analyst: list[Sentence] = Field(description="One to three sentences for an analyst: the numbers behind it.")


@dataclass(frozen=True)
class Card:
    """A draft with its placeholders filled in: what viewers see."""

    headline: str
    casual: str
    analyst: str
    plain: str  # for screen readers: the headline, then the casual line
    evidence: tuple[str, ...]  # events cited, then the events behind the facts used
    facts: tuple[str, ...]  # the fact keys used

    def to_json(self) -> dict:
        return {
            "headline": self.headline,
            "casual": self.casual,
            "analyst": self.analyst,
            "plain": self.plain,
            "evidence": list(self.evidence),
            "facts": list(self.facts),
        }


def placeholders(text: str) -> list[str]:
    return PLACEHOLDER.findall(text)


def fill(text: str, facts: Facts) -> str:
    return PLACEHOLDER.sub(lambda m: facts[m.group(1)].display, text)


def _sentences(draft: Draft) -> list[Sentence]:
    return [*draft.casual, *draft.analyst]


def render(draft: Draft, facts: Facts) -> Card:
    """Fill the draft's placeholders. Check the draft first: an unknown key raises KeyError."""
    headline = fill(draft.headline, facts).strip()
    casual = " ".join(fill(s.text, facts).strip() for s in draft.casual)
    analyst = " ".join(fill(s.text, facts).strip() for s in draft.analyst)
    used: list[str] = []
    for text in [draft.headline, *(s.text for s in _sentences(draft))]:
        for key in placeholders(text):
            if key not in used:
                used.append(key)
    evidence: list[str] = []
    for event_id in [e for s in _sentences(draft) for e in s.events] + [e for k in used for e in facts[k].events]:
        if event_id not in evidence:
            evidence.append(event_id)
    plain = f"{headline.rstrip('.')}. {casual}" if casual else headline
    return Card(headline, casual, analyst, plain, tuple(evidence), tuple(used))


def names_in(facts: Facts) -> frozenset[str]:
    """Every capitalised word in a fact's text: the names a card may write out itself."""
    words: set[str] = set(ALWAYS_ALLOWED)
    for fact in facts.values():
        if isinstance(fact.value, str):
            words.update(_bare(w) for w in _CAPITALISED.findall(fact.display))
    return frozenset(words)


def _bare(word: str) -> str:
    return word.removesuffix("'s").removesuffix("'").strip("-")


def _own_words(text: str) -> str:
    """The writer's own words: the text with its placeholders taken out."""
    return PLACEHOLDER.sub(" ", text)


def _text_problems(where: str, text: str, facts: Facts, names: frozenset[str]) -> list[str]:
    problems = []
    unknown = [key for key in placeholders(text) if key not in facts]
    if unknown:
        problems.append(
            f"{where}: unknown fact {', '.join('{' + k + '}' for k in unknown)}; use only keys the tools returned"
        )
    own = _own_words(text)
    if "{" in own or "}" in own:
        problems.append(f"{where}: a brace that isn't a whole placeholder; write placeholders as {{key}}")
    if _DIGIT.search(own):
        problems.append(f"{where}: a figure typed as digits in '{text}'; put every figure in as its placeholder")
    if (word := _NUMBER_WORD.search(own)) is not None:
        problems.append(f"{where}: the number '{word.group(0)}' written as a word; use a fact's placeholder")
    if _PERCENT_WORD.search(own):
        problems.append(f"{where}: 'per cent' written out; a share's placeholder already shows its % sign")
    if (word := _BETTING.search(own)) is not None:
        problems.append(f"{where}: betting language ('{word.group(0)}')")
    if "!" in own:
        problems.append(f"{where}: an exclamation mark; keep the tone calm")
    if _EMOJI.search(own) or _LINK.search(own):
        problems.append(f"{where}: emoji or a link")
    for m in _CAPITALISED.finditer(own):
        name = _bare(m.group(0))
        if name in names or _SENTENCE_START.search(own[: m.start()]):
            continue
        problems.append(f"{where}: '{name}' isn't a name from the facts; write names as the tools give them")
    return problems


def check(draft: Draft, facts: Facts, events: set[str] | frozenset[str]) -> list[str]:
    """What is wrong with the draft, or nothing.

    `facts` are the facts the writer was given and `events` the IDs of the events it was shown.
    """
    names = names_in(facts)
    problems = _text_problems("headline", draft.headline, facts, names)
    for part, sentences, (least, most) in (
        ("casual", draft.casual, CASUAL_SENTENCES),
        ("analyst", draft.analyst, ANALYST_SENTENCES),
    ):
        if not least <= len(sentences) <= most:
            problems.append(f"{part}: {len(sentences)} sentences; write {least} to {most}")
        for i, sentence in enumerate(sentences, start=1):
            where = f"{part} sentence {i}"
            if not sentence.text.strip():
                problems.append(f"{where}: empty")
                continue
            problems += _text_problems(where, sentence.text, facts, names)
            unseen = [e for e in sentence.events if e not in events]
            if unseen:
                problems.append(f"{where}: cites {', '.join(unseen)}, which no tool returned")
            if not sentence.events and not placeholders(sentence.text):
                problems.append(f"{where}: rests on nothing; cite the events behind it or use a fact")
    if problems:
        return problems
    card = render(draft, facts)
    for part, value, limit in (
        ("headline", card.headline, HEADLINE_CHARS),
        ("casual", card.casual, CASUAL_CHARS),
        ("analyst", card.analyst, ANALYST_CHARS),
    ):
        if not value:
            problems.append(f"{part}: empty")
        elif len(value) > limit:
            problems.append(f"{part}: {len(value)} characters once filled in; keep it to {limit}")
    return problems
