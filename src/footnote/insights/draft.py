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
- a fact's display carries its noun ("13 shots", "2 shots on target"), so the words after its
  placeholder don't say the noun again;
- capitals are for names: every capitalised word except a sentence's first is a name from the facts,
  and names written next to each other must be one name as a fact gives it ("Femi Adeyani", or
  "Adeyani" alone), so words from two names can't be joined into a third. A sentence's first word
  is held to this only when it is part of a name: an ordinary word in capitals can't be told from
  an unknown name without a dictionary. Filled in, the headline and every sentence start with a
  capital or a figure;
- every sentence rests on something: an event it cites, or a fact it uses; every event it cites is
  one the writer was shown; and when the facts rest on events, the card links to at least one;
- headline and lines fit their space, with no betting language, exclamations, links or emoji;
- the text is plain: no markup, no characters a reader can't see, no number characters other than
  the digits already refused, and no letters from outside the Latin alphabet, so a figure or a name
  can't get past the checks above in disguise (a circled digit, a fraction sign, a zero-width space
  inside "two", a Greek omicron in it, a name in small capitals);
- a card uses no fact its topic withholds: the catch-up for a viewer joining mid-match leaves the
  score out until the viewer asks for it.

How much a card may say depends on its topic (`limits_for`): a recap tells the story of a half and
gets more room than a moment's card.

The checks catch figures and names a writer made up. A real name from the match given to the wrong
player, or a sentence that reads the facts unfairly, passes them: that is for the evaluations of the
agents' output.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from fnmatch import fnmatchcase

from pydantic import BaseModel, ConfigDict, Field

from footnote.insights.facts import Facts

PLACEHOLDER = re.compile(r"\{([A-Za-z][A-Za-z0-9_\-]*(?:\.[A-Za-z0-9_\-]+)+)\}")

HEADLINE_CHARS = 60
CASUAL_CHARS = 240
ANALYST_CHARS = 360
CASUAL_SENTENCES = (1, 2)
ANALYST_SENTENCES = (1, 3)


@dataclass(frozen=True)
class Limits:
    """How much a card may say, and the facts its wording must leave out."""

    casual_sentences: tuple[int, int] = CASUAL_SENTENCES
    casual_chars: int = CASUAL_CHARS
    analyst_sentences: tuple[int, int] = ANALYST_SENTENCES
    analyst_chars: int = ANALYST_CHARS
    withheld: tuple[str, ...] = ()  # fact keys, as shell-style patterns
    withheld_because: str = ""


CARD = Limits()
# A recap tells the story of the match so far, so its casual line gets more room than a moment's.
RECAP_CHARS = 400
RECAP = Limits(casual_sentences=(1, 3), casual_chars=RECAP_CHARS)
# The catch-up for a viewer joining mid-match leaves the score out: the viewer chooses when to see it
# (docs/experience.md, "Catch-up").
CATCH_UP = Limits(
    casual_sentences=(1, 3),
    casual_chars=RECAP_CHARS,
    withheld=("score.*", "*.score_line"),
    withheld_because="the catch-up leaves the score out until the viewer asks for it",
)
LIMITS = {"half_time": RECAP, "full_time": RECAP, "catch_up": CATCH_UP}


def limits_for(topic: str) -> Limits:
    return LIMITS.get(topic, CARD)


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
# Where a card's letters may come from: the Latin alphabet with the accented letters names and
# French or Spanish words need. Small capitals and look-alike letters from other alphabets are
# outside it, so they can't stand in for a name or a number word.
_LATIN_LETTERS = ((0x41, 0x5A), (0x61, 0x7A), (0xC0, 0x24F), (0x1E00, 0x1EFF))


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


def same_words(a: str, b: str) -> bool:
    """Whether two lines say the same words, whatever their punctuation and capitals."""
    return re.sub(r"\W+", " ", a).strip().lower() == re.sub(r"\W+", " ", b).strip().lower()


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


# The words straight after a placeholder, as many as a fact's noun can have.
_NEXT_WORDS = re.compile(r"(?:\s+[^\W\d_]+){1,4}")


def _singular(word: str) -> str:
    word = word.lower()
    return word[:-2] if word.endswith("es") else word[:-1] if word.endswith("s") else word


def _doubled_nouns(where: str, text: str, facts: Facts) -> list[str]:
    """A count's display carries its noun ("44 passes", "2 shots on target"), so "{key} passes" or
    "{key} on target" would show it twice."""
    problems = []
    for m in PLACEHOLDER.finditer(text):
        fact = facts.get(m.group(1))
        following = _NEXT_WORDS.match(text, m.end())
        if fact is None or following is None:
            continue
        shown = fact.display.split()
        noun: list[str] = []  # the words that end the display, after its figure
        while len(shown) > 1 and len(noun) < len(shown) and shown[-1 - len(noun)].isalpha():
            noun.insert(0, shown[-1 - len(noun)])
        after = following.group(0).split()
        for n in range(min(len(noun), len(after)), 0, -1):
            if [_singular(w) for w in after[:n]] == [_singular(w) for w in noun[-n:]]:
                doubled = " ".join(after[:n])
                problems.append(
                    f"{where}: '{{{m.group(1)}}} {doubled}' shows as '{fact.display} {doubled}': the fact"
                    f" already shows its noun, so leave out '{doubled}'"
                )
                break
    return problems


def _latin(letter: str) -> bool:
    return any(low <= ord(letter) <= high for low, high in _LATIN_LETTERS)


def _character_problems(where: str, own: str) -> list[str]:
    problems = []
    if "<" in own or ">" in own:
        problems.append(f"{where}: markup ('<' or '>'); write plain text")
    hidden = sorted({f"U+{ord(c):04X}" for c in own if unicodedata.category(c) in ("Cc", "Cf")})
    if hidden:
        problems.append(f"{where}: characters a reader can't see ({', '.join(hidden)}); write plain text")
    # Digits are refused already; these are the other number characters: circled, fractions, superscripts.
    figures = [c for c in own if unicodedata.category(c).startswith("N") and not _DIGIT.match(c)]
    if figures:
        problems.append(f"{where}: a figure typed as '{figures[0]}'; put every figure in as its placeholder")
    letters = sorted({c for c in own if unicodedata.category(c).startswith("L") and not _latin(c)})
    if letters:
        problems.append(f"{where}: letters from outside the Latin alphabet ('{''.join(letters)}'); write plain English")
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


def _text_problems(where: str, text: str, facts: Facts, names: Names, limits: Limits) -> list[str]:
    problems = []
    unknown = [key for key in placeholders(text) if key not in facts]
    if unknown:
        problems.append(
            f"{where}: unknown fact {', '.join('{' + k + '}' for k in unknown)}; use only keys the tools returned"
        )
    withheld = [k for k in placeholders(text) if any(fnmatchcase(k, pattern) for pattern in limits.withheld)]
    if withheld:
        problems.append(f"{where}: uses {', '.join('{' + k + '}' for k in withheld)}; {limits.withheld_because}")
    problems += _doubled_nouns(where, text, facts)
    own = _own_words(text)
    if "{" in own or "}" in own:
        problems.append(f"{where}: a brace that isn't a whole placeholder; write placeholders as {{key}}")
    if _SENTENCE_BREAK.search(own.strip()):
        problems.append(f"{where}: more than one sentence; give each sentence its own entry, with its own events")
    problems += _figure_problems(where, own)
    problems += _character_problems(where, own)
    if (word := _BETTING.search(own)) is not None:
        problems.append(f"{where}: betting language ('{word.group(0)}')")
    if "!" in own:
        problems.append(f"{where}: an exclamation mark; keep the tone calm")
    if _EMOJI.search(own) or _LINK.search(own):
        problems.append(f"{where}: emoji or a link")
    problems += _name_problems(where, own, names)
    return problems


def check(draft: Draft, facts: Facts, events: set[str] | frozenset[str], limits: Limits = CARD) -> list[str]:
    """What is wrong with the draft, or nothing.

    `facts` are the facts the writer was given and `events` the IDs of the events it was shown;
    `limits` are the card's topic's (`limits_for`).
    """
    names = names_in(facts)
    problems = _text_problems("headline", draft.headline, facts, names, limits)
    for part, sentences, (least, most) in (
        ("casual", draft.casual, limits.casual_sentences),
        ("analyst", draft.analyst, limits.analyst_sentences),
    ):
        if not least <= len(sentences) <= most:
            problems.append(f"{part}: {len(sentences)} sentences; write {least} to {most}")
        for i, sentence in enumerate(sentences, start=1):
            where = f"{part} sentence {i}"
            if not sentence.text.strip():
                problems.append(f"{where}: empty")
                continue
            problems += _text_problems(where, sentence.text, facts, names, limits)
            unseen = [e for e in sentence.events if e not in events]
            if unseen:
                problems.append(f"{where}: cites {', '.join(unseen)}, which no tool returned")
            if not sentence.events and not placeholders(sentence.text):
                problems.append(f"{where}: rests on nothing; cite the events behind it or use a fact")
    if problems:
        return problems
    # A placeholder can open a sentence with its fact's display, which may start in lower case.
    for where, text in [("headline", draft.headline)] + [
        (f"{part} sentence {i}", sentence.text)
        for part, sentences in (("casual", draft.casual), ("analyst", draft.analyst))
        for i, sentence in enumerate(sentences, start=1)
    ]:
        filled = fill(text, facts).strip()
        lead = _LEAD.match(filled)
        if filled[lead.end() if lead else 0 :][:1].islower():
            problems.append(f"{where}: starts in lower case once filled in ('{filled[:30]}'); start with a capital")
    card = render(draft, facts)
    for part, value, limit in (
        ("headline", card.headline, HEADLINE_CHARS),
        ("casual", card.casual, limits.casual_chars),
        ("analyst", card.analyst, limits.analyst_chars),
    ):
        if not value:
            problems.append(f"{part}: empty")
        elif len(value) > limit:
            problems.append(f"{part}: {len(value)} characters once filled in; keep it to {limit}")
    if not card.evidence and any(fact.events for fact in facts.values()):
        problems.append("the card links to no event; cite the events behind it, or use a fact that rests on them")
    return problems
