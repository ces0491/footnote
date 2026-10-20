"""A card's wording, and the checks it passes before anyone sees it.

A draft is a headline, a line for casual fans and a line for analysts, each sentence listing the
events it rests on. Where a figure goes, the wording has a placeholder naming a fact,
`{teams.SAL.possession}`, never the figure itself: `render` fills placeholders in from the facts, so
the figures on a card are always code's (facts.py). Templates write drafts this way (templates.py),
and so do the agents.

`check` lists what is wrong with a draft, in words an agent can act on:

- every placeholder names a fact the writer was given, and the writer typed no figure of its own:
  no digits, no numbers or ordinals spelled out ("one", "nil", "first goal"), no shares in words
  ("half the ball", "per cent"), and no "brace" or "hat-trick". Phrases that use those words without
  stating a figure, such as "first half", "one of" and "final third", are allowed;
- each sentence is its own entry;
- capitals are for names: every capitalised word except a sentence's first is a name from the facts,
  and names written next to each other must be one name as a fact gives it ("Femi Adeyani", or
  "Adeyani" alone), so words from two names can't be joined into a third. A sentence's first word
  is held to this only when it is part of a name: an ordinary word in capitals can't be told from
  an unknown name without a dictionary;
- every sentence rests on something: an event it cites, or a fact it uses; every event it cites is
  one the writer was shown; and when the facts rest on events, the card links to at least one;
- headline and lines fit their space, with no betting language, exclamations, links or emoji.

The checks catch figures and names a writer made up. A real name from the match given to the wrong
player, or a sentence that reads the facts unfairly, passes them: that is for the evaluations of the
agents' output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from footnote.insights.facts import Facts

PLACEHOLDER = re.compile(r"\{([A-Za-z][A-Za-z0-9_\-]*(?:\.[A-Za-z0-9_\-]+)+)\}")

HEADLINE_CHARS = 60
CASUAL_CHARS = 240
ANALYST_CHARS = 360
CASUAL_SENTENCES = (1, 2)
ANALYST_SENTENCES = (1, 3)

_DIGIT = re.compile(r"\d")
_NUMBER_WORD = re.compile(
    r"\b(?:zero|nil|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
    r"fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
    r"hundred|thousand|million|dozen|twice|thrice|brace|hat-trick|hat trick|hattrick|"
    r"first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth|thirteenth|"
    r"fourteenth|fifteenth|sixteenth|seventeenth|eighteenth|nineteenth|twentieth|thirtieth|fortieth|"
    r"fiftieth|sixtieth|seventieth|eightieth|ninetieth|hundredth)\b",
    re.IGNORECASE,
)
# Phrases that use a number word without stating a figure; taken out before the check above.
_NUMBER_IDIOM = re.compile(
    r"\b(?:no one|one of|one another|one-two|one-twos|one-on-one|one-touch|(?:first|second)[- ]half|"
    r"first[- ]touch|first-time|second balls?|second yellow|(?:final|middle|attacking|defensive) third|"
    r"third[- ]man)\b",
    re.IGNORECASE,
)
# A share in words: "half the ball", "a quarter of the passes".
_FRACTION = re.compile(r"\b(?:half|quarters?)\s+(?:of|the|their|its|his|her|our|an|a|as|all)\b", re.IGNORECASE)
_PERCENT_WORD = re.compile(r"\bper\s?cent\b", re.IGNORECASE)
_BETTING = re.compile(
    r"\b(bet|bets|betting|odds|bookmakers?|bookies?|wagers?|punters?|accumulators?|stake|stakes)\b",
    re.IGNORECASE,
)
_EMOJI = re.compile(f"[{chr(0x1F000)}-{chr(0x1FAFF)}{chr(0x2600)}-{chr(0x27BF)}]")
_LINK = re.compile(r"https?://|www\.", re.IGNORECASE)
# One sentence ends and another begins.
_SENTENCE_BREAK = re.compile(r"[.?!]\s+\S")

_APOSTROPHES = "'" + chr(0x2019)
# A word: letters in any alphabet, with apostrophes and hyphens inside it ("O'Neill", "Half-time").
_WORD = re.compile(f"[^\\W\\d_](?:[^\\W\\d_]|[{_APOSTROPHES}-](?=[^\\W\\d_]))*")
# What may come before a sentence's first word: spaces, an opening bracket or quotation mark.
_LEAD = re.compile("[\\s(\"'" + chr(0x2018) + chr(0x201C) + "]*")
# Stands for a placeholder in the writer's own words, so a name can't run across one.
_PLACEHOLDER_MARK = f" {chr(0xFFFC)} "
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


@dataclass(frozen=True)
class Names:
    """The names a card may write out: each as a fact shows it, and the words they are made of."""

    sequences: frozenset[tuple[str, ...]]
    words: frozenset[str]

    def has(self, run: tuple[str, ...]) -> bool:
        """Whether `run` is one name, or a part of one in order: "Femi Adeyani", or "Adeyani"."""
        n = len(run)
        return any(name[i : i + n] == run for name in self.sequences for i in range(len(name) - n + 1))


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


def _bare(word: str) -> str:
    """A word without its possessive: "Varlan's" is "Varlan"."""
    for apostrophe in _APOSTROPHES:
        if word.endswith(apostrophe + "s"):
            return word[:-2]
    return word


def _runs(text: str) -> list[list[tuple[str, int]]]:
    """Runs of capitalised words with only spaces between them, each word bare and with its offset.

    Anything else between two words ends a run, and so does a possessive, so "Saltmarsh's Teo
    Varlan" is two runs. The words in ALWAYS_ALLOWED stand on their own.
    """
    runs: list[list[tuple[str, int]]] = []
    current: list[tuple[str, int]] = []
    end, possessive = 0, False
    for m in _WORD.finditer(text):
        word, gap = m.group(0), text[end : m.start()]
        end = m.end()
        if current and (possessive or gap.strip()):
            runs.append(current)
            current = []
        bare = _bare(word)
        possessive = bare != word
        if word[0].isupper() and bare not in ALWAYS_ALLOWED:
            current.append((bare, m.start()))
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return runs


def names_in(facts: Facts) -> Names:
    """The names the facts' texts hold: what a card may write out itself."""
    sequences = {
        tuple(word for word, _ in run)
        for fact in facts.values()
        if isinstance(fact.value, str)
        for run in _runs(fact.display)
    }
    return Names(frozenset(sequences), frozenset(word for name in sequences for word in name))


def _own_words(text: str) -> str:
    """The writer's own words: the text with each placeholder taken out."""
    return PLACEHOLDER.sub(_PLACEHOLDER_MARK, text)


def _figure_problems(where: str, own: str) -> list[str]:
    problems = []
    if _DIGIT.search(own):
        problems.append(f"{where}: a figure typed as digits; put every figure in as its placeholder")
    plain = _NUMBER_IDIOM.sub(" ", own)
    if (word := _NUMBER_WORD.search(plain)) is not None:
        problems.append(f"{where}: the number '{word.group(0)}' written as a word; use a fact's placeholder")
    if (share := _FRACTION.search(plain)) is not None:
        problems.append(f"{where}: a share written in words ('{share.group(0)}'); use a fact's placeholder")
    if _PERCENT_WORD.search(own):
        problems.append(f"{where}: 'per cent' written out; a share's placeholder already shows its % sign")
    return problems


def _name_problems(where: str, own: str, names: Names) -> list[str]:
    problems = []
    first = _LEAD.match(own)
    start = first.end() if first else 0
    for run in _runs(own):
        words = tuple(word for word, _ in run)
        if run[0][1] == start and words[0] not in names.words:
            words = words[1:]  # an ordinary word starting the sentence, or a name nobody can tell from one
        unknown = [word for word in words if word not in names.words]
        for word in unknown:
            problems.append(f"{where}: '{word}' isn't a name from the facts; write names as the tools give them")
        if words and not unknown and not names.has(words):
            problems.append(
                f"{where}: '{' '.join(words)}' isn't a name as any one fact gives it; write each name as a fact shows it"
            )
    return problems


def _text_problems(where: str, text: str, facts: Facts, names: Names) -> list[str]:
    problems = []
    unknown = [key for key in placeholders(text) if key not in facts]
    if unknown:
        problems.append(
            f"{where}: unknown fact {', '.join('{' + k + '}' for k in unknown)}; use only keys the tools returned"
        )
    own = _own_words(text)
    if "{" in own or "}" in own:
        problems.append(f"{where}: a brace that isn't a whole placeholder; write placeholders as {{key}}")
    if _SENTENCE_BREAK.search(own.strip()):
        problems.append(f"{where}: more than one sentence; give each sentence its own entry, with its own events")
    problems += _figure_problems(where, own)
    if (word := _BETTING.search(own)) is not None:
        problems.append(f"{where}: betting language ('{word.group(0)}')")
    if "!" in own:
        problems.append(f"{where}: an exclamation mark; keep the tone calm")
    if _EMOJI.search(own) or _LINK.search(own):
        problems.append(f"{where}: emoji or a link")
    problems += _name_problems(where, own, names)
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
    if not card.evidence and any(fact.events for fact in facts.values()):
        problems.append("the card links to no event; cite the events behind it, or use a fact that rests on them")
    return problems
