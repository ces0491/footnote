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
  placeholder don't say the noun, or part of it, again ("31 passes completed passes"), and a word
  for one thing doesn't go before it ("74% of a 5 minutes"); a minute after a verb such as "began"
  takes "at", and its display has the minute mark, so none follows it ("from 17''"); a spell's length
  isn't where the minute it ended would go ("from 2' to 5 minutes"); a count of times follows what
  happened, not a form of "be" ("there were 7 times");
  "only" doesn't go before a count of none ("only no shots"); and a score line, which names both clubs, doesn't follow a verb ("Kingsferry lead Saltmarsh 1–2
  Kingsferry") or "to" ("turns the game to Saltmarsh 1–2 Kingsferry"); a goal's situation, said of
  its club, doesn't follow "have" ("the goal that would have equalise");
- the ball changing hands counts both sides losing it, so no side "forced" it;
- "effort" isn't written for a shot or a goal: the Translator gave it as a counter-attack, and as a
  shot VAR annulled;
- a sentence saying a goal was ruled out uses the facts of the VAR decision that ruled it out (its
  player or its minute), so it can't pin the decision on a goal that stands;
- a VAR check for a penalty is about whether its subject gave one away, so no penalty is "for" or
  "to" that player ("VAR rejected a penalty for Uche Asatoye");
- a card that says who a goal is credited to also says who it was credited to before, when its
  facts have a correction: "later credited to Femi Adeyani" alone reads as if it always had been. The
  earlier credit doesn't come after "not", "instead of" or "rather than", or in brackets, where it
  reads aloud as the scorer, and the goal isn't "corrected to" or "credited to" the scorer the
  sentence has already named;
- wording a writer would only have copied from the tools is refused: "shown as" from a fact's
  description, the model's name, a count of times followed by a noun ("7 times changes of
  possession"), a spell's length before the word for it ("a 5 minutes spell"), a heading fact
  such as "No penalty", or the template's list of goals, in the middle of a sentence, and in a
  recap "the last {story.3.window}", which was the stretch before that spell, not before now;
- filled in, "a" doesn't go before a vowel or a figure said with one ("a own goal", "a 80% chance"),
  no word comes twice in a row ("a counter counter"), and no name is joined to itself ("Saltmarsh
  and later Saltmarsh");
- a long text fact, such as the provider's reason, is given in one line, not both;
- capitals are for names: every capitalised word except a sentence's first is a name from the facts,
  and names written next to each other must be one name as a fact gives it ("Femi Adeyani", or
  "Adeyani" alone), so words from two names can't be joined into a third. A sentence's first word
  is held to this only when it is part of a name: an ordinary word in capitals can't be told from
  an unknown name without a dictionary. Filled in, the headline and every sentence start with a
  capital or a figure, and VAR is in capitals wherever it is;
- every sentence rests on something: an event it cites, or a fact it uses; every event it cites is
  one the writer was shown; and when the facts rest on events, the card links to at least one;
- headline and lines fit their space, with no betting language, exclamations, links or emoji;
- the text is plain: no markup, no characters a reader can't see, no number characters other than
  the digits already refused, and no letters from outside the Latin alphabet, so a figure or a name
  can't get past the checks above in disguise (a circled digit, a fraction sign, a zero-width space
  inside "two", a Greek omicron in it, a name in small capitals);
- a card uses no fact its topic withholds: the catch-up for a viewer joining mid-match tells what
  happened and leaves the score line to the scoreboard beside it.

How much a card may say depends on its topic (`limits_for`): a recap tells the story of a half and
gets more room than a moment's card.

A recap's casual line ends with code's own sentence on each goal the data provider credited to
another player (templates.told), so the writer's checker (agents/writer.py) also refuses a recap whose
own sentences tell that change again (`retold`): one that speaks of a credit or a correction, or
names the earlier credit through its fact.

The checks catch figures and names a writer made up, a goal ruled out pinned on one that stands, and
a penalty check's player written as the one it was for. Any other real name from the match given to
the wrong player, or a sentence that reads the facts unfairly, passes them: the evaluations of the
agents' output catch some of that, and reading the cards catches the rest (docs/evaluations.md).
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
# The catch-up for a viewer joining mid-match tells what happened, and the scoreboard beside it shows
# the score, so its wording leaves the score line out (docs/experience.md, "Catch-up").
CATCH_UP = Limits(
    casual_sentences=(1, 3),
    casual_chars=RECAP_CHARS,
    withheld=("score.*", "*.score_line"),
    withheld_because="the catch-up tells what happened and leaves the score line to the scoreboard beside it",
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
# VAR in any other casing: sentence case turned one writer's headline into "Var: No penalty".
_VAR_MISCASED = re.compile(r"\b(?!VAR\b)[Vv][Aa][Rr]\b")
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
    """A noun's singular, near enough to compare two: "passes" and "pass", "changes" and "change"."""
    word = word.lower()
    if word.endswith("ss"):
        return word
    if word.endswith("es") and word[:-2].endswith(("s", "x", "z", "ch", "sh")):
        return word[:-2]
    return word[:-1] if word.endswith("s") else word


# Words that can come between a count and a noun of its own: "{key} and passes" isn't the noun twice.
_LINKS = frozenset("and or but while with to from of in on at by for than as the a an their its".split())


def _doubled_nouns(where: str, text: str, facts: Facts) -> list[str]:
    """A count's display carries its noun ("44 passes", "2 shots on target"), so "{key} passes",
    "{key} shots", "{key} on target" or "{key} completed passes" would show it, or part of it, twice."""
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
        words = following.group(0).split()
        after = [_singular(w) for w in words]
        said = [_singular(w) for w in noun]
        # The noun's last words ("on target") or its first ("shots" in "5 shots on target").
        for n in range(min(len(noun), len(after)), 0, -1):
            if after[:n] == said[-n:] or after[:n] == said[:n]:
                doubled = " ".join(words[:n])
                problems.append(
                    f"{where}: '{{{m.group(1)}}} {doubled}' shows as '{fact.display} {doubled}': the fact"
                    f" already shows its noun, so leave out '{doubled}'"
                )
                break
        else:
            # The noun again after a word or two of its own: "31 passes completed passes".
            for n in (1, 2):
                if said and len(after) > n and after[n] == said[-1] and not _LINKS & {w.lower() for w in words[:n]}:
                    doubled = " ".join(words[: n + 1])
                    problems.append(
                        f"{where}: '{{{m.group(1)}}} {doubled}' shows as '{fact.display} {doubled}': the fact"
                        f" already shows its noun, so leave out '{doubled}', or put the words before the placeholder"
                    )
                    break
    return problems


# Wording a writer copied from the tools rather than wrote: a fact's description ("shown as on
# top") and the model's name, which means nothing to a viewer and translated as "modelo de estado
# de coincidencia" and "modèle d'État".
_COPIED = re.compile(r"\bshown as\b|\b(?:match[- ])?state model\b", re.IGNORECASE)
# "Effort" for a shot or a goal: "an 89.1 km/h effort on a counter" came back as "une contre-attaque
# de 89,1 km/h", and "ruled out a Saltmarsh effort" as "anuló un disparo" (annulled a shot).
_EFFORT = re.compile(r"\befforts?\b", re.IGNORECASE)
# A spell's length where the minute it ended would go: "from {story.1.start_minute} to
# {story.1.window}" read "from 2' to 5 minutes", and came back as "from the 2nd to the 5th minute".
_FROM_TO = re.compile(r"\bfrom \{([\w.\-]+)\} (?:to|until|till) \{([\w.\-]+)\}", re.IGNORECASE)
# What may follow a count of times ("7 times", "once"): it says how often, so a noun after it reads
# as "forced 7 times changes of possession".
_AFTER_TIMES = frozenset(
    "in during over while as and but or since before after with within across each per so that this there"
    " then when already now again for from on at inside to by".split()
)
# A spell's length before the word for it: "a 5 minutes spell".
_SPELL_WORDS = frozenset({"spell", "spells", "period", "periods", "stretch", "burst", "run"})
_DURATION = re.compile(r"^\d+ (?:minutes|seconds)$")
# A count as a fact shows it, with its noun ("5 minutes", "4 passes", "no shots", "once"), after a
# word for one thing: "74% of a 5 minutes", "51% of that 3 minutes".
_COUNTED = re.compile(r"^(?:\d+|no) [^\W\d_]+(?: [^\W\d_]+)*$|^once$")
_ONE_OF = frozenset({"a", "an", "that", "this", "each", "every"})
_WORD_BEFORE = re.compile(r"([^\W\d_]+)\s+$")
# Verbs that need "at" before a minute: "the spell began 64'", "the 3 minutes starting 46'".
_AT_VERBS = frozenset(
    "began begun begins beginning started starts starting ended ends ending came comes scored scores struck"
    " strikes levelled levels equalised equalises".split()
)
# A count of times after a form of "be" says nothing happened: "there were 7 times".
_BE = frozenset("is are was were be been being".split())
# A verb before a score line, which names both clubs: "Kingsferry lead Saltmarsh 1–2 Kingsferry".
_SCORE_VERBS = frozenset("lead leads led leading trail trails trailed trailing beat beats beating".split())
# "To" before one: "turns the game to Saltmarsh 1–2 Kingsferry" came back from the Translator as "a
# favor de" and "en faveur de" the score line, one club's lead.
# A goal's situation ("equalise", "take the lead") is said of its club; after "have" it read "the goal
# that would have equalise".
_HAVE = frozenset("have has had having".split())
# The ball changing hands counts both sides losing it, so no side forced it.
_FORCED = re.compile(r"\bforc\w*\s+(?:the ball to change hands|\{[\w.]*changes\})", re.IGNORECASE)
# A text fact long enough that giving it in both lines repeats a sentence: the provider's reason.
_LONG_TEXT_WORDS = 6
# Facts worded as a heading ("No penalty", "Final score"), which mid-sentence read "ended No
# penalty": a sentence may give one only after a colon. By the fact's name, so a recap's
# `story.5.decision_text` is one too.
HEADING_FACTS = frozenset({"decision_text", "label"})
# The template's list of goals, which opening a sentence read "Femi Adeyani (Kingsferry) 23' Javi
# Ferrano played the final pass": after a colon too.
LIST_FACTS = frozenset({"recap.goals"})
# A spell's wording in the story is as of its moment: in a recap, "the last {story.3.window}" read
# as the minutes before the recap.
_STORY_LAST = re.compile(r"\b(?:the )?(?:last|past|previous|preceding) \{(story\.\d+)\.window\}", re.IGNORECASE)
# Figures said with a vowel sound: eight, eleven, eighteen, eighty-something.
_AN_FIGURE = re.compile(r"8|1[18](?!\d)")
# "A" before a vowel or such a figure once filled in ("a own goal", "a 80% chance"); words spelt
# with a vowel but said with a consonant are let be.
_NEEDS_AN = re.compile(rf"\b(a) ((?!one\b|once\b|uni|use|usu|eu)(?:[aeiou]|{_AN_FIGURE.pattern})\S*)", re.IGNORECASE)


# A word twice in a row once filled in: "finished a {story.4.play_pattern} counter" read "a counter
# counter". "Had had" and "that that" can be right.
_TWICE = re.compile(r"\b(?!(?:had|that)\b)([^\W\d_]+)\s+\1\b", re.IGNORECASE)
# A name joined to itself once filled in: "{story.1.club} and later {story.3.club}" read "Saltmarsh
# and later Saltmarsh".
_SELF_JOINED = re.compile(r"\b([A-Z][^\W\d_]+) and (?:[^\W\d_]+ ){0,2}\1\b")


def indefinite(display: str) -> str:
    """The article before a figure as it is read: "an 8% chance", "a 5% chance"."""
    return "an" if _AN_FIGURE.match(display) else "a"


def _named(key: str) -> str:
    """A fact's name without its prefix: "decision_text" for `story.5.decision_text`."""
    return key.rsplit(".", 1)[-1]


def _score_line(key: str) -> bool:
    """Whether a fact is a score line naming both clubs: `moment.score_line`, `score.line`."""
    return _named(key) == "score_line" or key == "score.line"


def _misplaced_counts(where: str, text: str, facts: Facts) -> list[str]:
    """A count of times followed by a noun, a spell's length followed by the word "spell", and a
    count after a word for one thing ("a 5 minutes")."""
    problems = []
    for m in PLACEHOLDER.finditer(text):
        fact = facts.get(m.group(1))
        if fact is None:
            continue
        before = _WORD_BEFORE.search(text, 0, m.start())
        after = _NEXT_WORDS.match(text, m.end())
        # "A {window} spell" has its own advice below: "a spell of {window}".
        spell = after is not None and after.group(0).split()[0].lower() in _SPELL_WORDS
        if before is not None and before.group(1).lower() in _ONE_OF and _COUNTED.match(fact.display) and not spell:
            word = before.group(1)
            plural = {"that": "those", "this": "these"}.get(word.lower())
            problems.append(
                f"{where}: '{word} {{{m.group(1)}}}' shows as '{word} {fact.display}': the fact gives its own number,"
                + (f" so write '{plural} {{{m.group(1)}}}'" if plural else f" so leave out '{word}'")
            )
        if before is not None and before.group(1).lower() in _AT_VERBS and fact.display.endswith("'"):
            problems.append(
                f"{where}: '{before.group(1)} {{{m.group(1)}}}' shows as '{before.group(1)} {fact.display}'; write"
                f" '{before.group(1)} at {{{m.group(1)}}}'"
            )
        # A minute mark typed after a minute's placeholder: "dominating possession from 17''".
        if fact.display.endswith("'") and m.end() < len(text) and text[m.end()] in _APOSTROPHES:
            problems.append(
                f"{where}: '{{{m.group(1)}}}{text[m.end()]}' shows as '{fact.display}{text[m.end()]}': the fact shows"
                " its minute mark, so leave out the one after it"
            )
        # "Only" before a count of none: "they registered only no shots".
        if before is not None and before.group(1).lower() == "only" and fact.display.startswith("no "):
            problems.append(f"{where}: 'only {{{m.group(1)}}}' shows as 'only {fact.display}'; leave out 'only'")
        times = fact.display == "once" or fact.display.endswith(" times")
        if before is not None and before.group(1).lower() in _BE and times:
            problems.append(
                f"{where}: '{before.group(1)} {{{m.group(1)}}}' shows as '{before.group(1)} {fact.display}': say what"
                f" happened before it ('the ball changed hands {{{m.group(1)}}}')"
            )
        if before is not None and before.group(1).lower() in _SCORE_VERBS and _score_line(m.group(1)):
            problems.append(
                f"{where}: '{before.group(1)} {{{m.group(1)}}}' shows as '{before.group(1)} {fact.display}', a club"
                f" named twice; give the score on its own ('{{{m.group(1)}}}: ...')"
            )
        if before is not None and before.group(1).lower() == "to" and _score_line(m.group(1)):
            problems.append(
                f"{where}: 'to {{{m.group(1)}}}' shows as 'to {fact.display}'; give the score on its own"
                f" ('{{{m.group(1)}}}: ...'), or end the clause with ', making it {{{m.group(1)}}}'"
            )
        if before is not None and before.group(1).lower() in _HAVE and _named(m.group(1)) == "situation":
            problems.append(
                f"{where}: '{before.group(1)} {{{m.group(1)}}}' shows as '{before.group(1)} {fact.display}'; the fact"
                f" is said of the club, so write it after the club's name ('Saltmarsh {fact.display}')"
            )
        following = _NEXT_WORDS.match(text, m.end())
        if following is None:
            continue
        word = following.group(0).split()[0]
        if (fact.display == "once" or fact.display.endswith(" times")) and word.lower() not in _AFTER_TIMES:
            problems.append(
                f"{where}: '{{{m.group(1)}}} {word}' shows as '{fact.display} {word}': the fact says how often,"
                f" so say what happened before it ('the ball changed hands {{{m.group(1)}}}')"
            )
        elif _DURATION.match(fact.display) and word.lower() in _SPELL_WORDS:
            problems.append(
                f"{where}: '{{{m.group(1)}}} {word}' shows as '{fact.display} {word}'; write 'a {word} of"
                f" {{{m.group(1)}}}'"
            )
    return problems


# Words that say a goal was taken away.
_RULED_OUT = re.compile(r"\bruled out\b|\bdisallow|\bchalked off\b|\bstruck off\b", re.IGNORECASE)


def _ruled_out_problems(where: str, text: str, facts: Facts) -> list[str]:
    """A sentence saying a goal was ruled out names the VAR decision that ruled it out, through that
    decision's facts. The goals a recap is given are the ones that stand (a goal VAR ruled out is told
    by its decision), so "{story.4.scorer} scored at {story.4.minute}, a goal later ruled out by VAR"
    pins the wrong goal on the wrong player: it happened in a live catch-up."""
    if not _RULED_OUT.search(_own_words(text)):
        return []
    decisions = sorted(
        key.removesuffix(".decision")
        for key, fact in facts.items()
        if key.endswith(".decision") and fact.value == "no_goal"
    )
    used = placeholders(text)
    if any(key.startswith(d + ".") for d in decisions for key in used):
        return []
    if not decisions:
        return [f"{where}: says a goal was ruled out, but no VAR decision in the facts ruled one out"]
    named = [k for d in decisions for k in (f"{d}.subject", f"{d}.minute") if k in facts]
    return [
        f"{where}: says a goal was ruled out without the facts of the VAR decision that ruled it out;"
        f" name it with them ({', '.join('{' + k + '}' for k in named) or decisions[0]}), not with a goal"
        " that stands"
    ]


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
    problems += _ruled_out_problems(where, text, facts)
    problems += _misplaced_counts(where, text, facts)
    for m in _STORY_LAST.finditer(text):
        problems.append(
            f"{where}: '{m.group(0)}' reads as the minutes before now; say when the spell was, from"
            f" {{{m.group(1)}.start_minute}}"
        )
    for m in _FROM_TO.finditer(text):
        start, length = facts.get(m.group(1)), facts.get(m.group(2))
        if start is not None and length is not None and start.display.endswith("'") and _DURATION.match(length.display):
            problems.append(
                f"{where}: '{m.group(0)}' shows as 'from {start.display} to {length.display}', as if the spell ended at"
                f" a minute; {{{m.group(2)}}} is how long it lasted, so write 'a spell of {{{m.group(2)}}} from"
                f" {{{m.group(1)}}}'"
            )
    if (forced := _FORCED.search(text)) is not None:
        problems.append(
            f"{where}: '{forced.group(0)}': the ball changing hands counts both sides losing it, so no side forced"
            " it; say how often it changed hands"
        )
    own = _own_words(text)
    if (copied := _COPIED.search(own)) is not None:
        problems.append(f"{where}: '{copied.group(0)}' is the tools' wording; say what it means for the match")
    if (effort := _EFFORT.search(own)) is not None:
        problems.append(
            f"{where}: '{effort.group(0)}' came back from the Translator as a counter-attack, and as a shot VAR"
            " annulled; write 'shot', or 'goal' for one that went in"
        )
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
    if (var := _VAR_MISCASED.search(own)) is not None:
        problems.append(f"{where}: '{var.group(0)}' is VAR, written in capitals")
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
            for m in PLACEHOLDER.finditer(sentence.text):
                key = m.group(1)
                if sentence.text[: m.start()].rstrip().endswith(":"):
                    continue
                if _named(key) in HEADING_FACTS:
                    problems.append(
                        f"{where}: {{{key}}} is a heading ('{facts[key].display}'), not words for a sentence; say it"
                        " in your own words"
                        if key in facts
                        else f"{where}: {{{key}}} is a heading, not words for a sentence"
                    )
                elif key in LIST_FACTS:
                    problems.append(
                        f"{where}: {{{key}}} is the template's list, not words for a sentence; tell each goal with"
                        " its own facts"
                    )
    in_both = {k for s in draft.casual for k in placeholders(s.text)} & {
        k for s in draft.analyst for k in placeholders(s.text)
    }
    for key in sorted(in_both):
        fact = facts.get(key)
        if fact is not None and isinstance(fact.value, str) and len(fact.display.split()) >= _LONG_TEXT_WORDS:
            problems.append(f"{{{key}}} is in both lines; give it once, in the line it suits")
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
        if (article := _NEEDS_AN.search(filled)) is not None:
            problems.append(f"{where}: '{article.group(0)}' once filled in; write 'an' before it")
        if (twice := _TWICE.search(filled)) is not None:
            problems.append(
                f"{where}: '{twice.group(0)}' once filled in; a fact's display already says the word, so write it once"
            )
        if (joined := _SELF_JOINED.search(filled)) is not None:
            problems.append(f"{where}: '{joined.group(0)}' once filled in; both facts name the same, so say it once")
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
    problems += _credit_problems(card, facts)
    problems += _penalty_side_problems(card, facts)
    return problems


def _penalty_side_problems(card: Card, facts: Facts) -> list[str]:
    """A VAR check for a penalty is about whether its subject gave one away, so a penalty is never
    "for" or "to" them: a catch-up's "VAR rejected a penalty for Uche Asatoye" gave the 75' check to
    the wrong side."""
    text = " ".join((card.headline, card.casual, card.analyst))
    problems = []
    for key, fact in sorted(facts.items()):
        check = facts.get(key.rsplit(".", 1)[0] + ".check")
        if _named(key) != "subject" or check is None or check.value != "penalty":
            continue
        surname = re.escape(fact.display.split()[-1])
        wrong = re.search(rf"\bpenalt\w*\s+(?:for|to)\s+(?:[A-Z][^\W\d_]+\s+)*{surname}\b", text)
        if wrong is not None:
            problems.append(
                f"'{wrong.group(0)}': VAR checked whether {fact.display} gave a penalty away, so the penalty"
                f" isn't theirs; say what VAR found about {fact.display}"
            )
    return problems


# A goal the data provider credited afresh, told with its new credit alone ("later credited to Femi
# Adeyani"), reads as if it had always been that player's.
_CREDIT = re.compile(r"\bcredit", re.IGNORECASE)
# The earlier credit after a word that denies it, in the same clause: "now credited to Femi Adeyani,
# not Jory Penhallow" read aloud as if Penhallow were the scorer.
_DENIED = re.compile(r"\b(not|instead of|rather than)\b[^.;:,()]*$", re.IGNORECASE)


def _credit_problems(card: Card, facts: Facts) -> list[str]:
    """A card that says who a goal is credited to also says who it was credited to before, when the
    facts it was given have a correction (`correction.before`, or a recap's `story.<n>.before`), and
    doesn't give the earlier credit after "not" or in brackets: "(originally given as Jory Penhallow)"
    reads as another name for the scorer, and the Translator gave it as "originally called"."""
    text = " ".join((card.headline, card.casual, card.analyst))
    problems = []
    for key, fact in sorted(facts.items()):
        if _named(key) != "before" or not isinstance(fact.value, str):
            continue
        surname = fact.display.split()[-1]
        if _CREDIT.search(text) and surname not in text:
            problems.append(
                f"the card says who a goal is credited to but not who it was originally credited to; give {{{key}}} too"
            )
        for m in re.finditer(rf"\b{re.escape(surname)}\b", text):
            said = text[: m.start()]
            denied = _DENIED.search(said)
            if denied or (said.rfind("(") > said.rfind(")") and ")" in text[m.end() :]):
                where = f"after '{denied.group(1)}'" if denied else "in brackets"
                problems.append(
                    f"{where}, the earlier credit ({fact.display}) reads aloud as the scorer; say the goal was"
                    f" originally credited to {{{key}}}"
                )
                break
    # Each part's sentences: a headline has no full stop, and "Corrected: Femi Adeyani" run into the
    # casual line's "The 81' goal is now credited to Femi Adeyani" would read as one sentence.
    sentences = [s for part in (card.headline, card.casual, card.analyst) for s in re.split(r"(?<=[.!?])\s+", part)]
    for key, fact in sorted(facts.items()):
        if _named(key) != "after" or not isinstance(fact.value, str):
            continue
        # The scorer named, then the goal "corrected to" or "credited to" the same name: "Femi Adeyani's
        # strike at 81', later corrected to Femi Adeyani" and "Femi Adeyani restored Kingsferry's lead at
        # 81'; the goal was later credited to Femi Adeyani" say nothing about what changed.
        surname = re.escape(fact.display.split()[-1])
        for sentence in sentences:
            again = re.search(rf"\b(?:corrected|credited) to (?:credit )?(?:[A-Z][^\W\d_]+ )*{surname}\b", sentence)
            if again is not None and re.search(rf"\b{surname}\b", sentence[: again.start()]):
                problems.append(
                    f"'{again.group(0)}' after naming {fact.display} as the scorer says nothing changed; say"
                    f" the goal was originally credited to {{{key.rsplit('.', 1)[0]}.before}}"
                )
                break
    return problems


# Words that tell a goal was credited afresh.
_CREDIT_CHANGE = re.compile(r"\b(?:credit\w*|re-?credited|corrected|correction|amend\w*|originally)\b", re.IGNORECASE)


def retold(draft: Draft, told: list[Sentence], facts: Facts) -> list[str]:
    """Where a recap's writer tells a change of credit that code tells already: `told` are code's
    sentences, which end the casual line (templates.told), and `draft` is the writer's without them.
    A sentence of the writer's that speaks of a credit or a correction, or names the earlier credit
    through its fact, would tell the change twice."""
    if not told:
        return []
    said = " ".join(fill(s.text, facts) for s in told)
    problems = []
    for part, sentences in (("casual", draft.casual), ("analyst", draft.analyst)):
        for i, sentence in enumerate(sentences, start=1):
            earlier = [k for k in placeholders(sentence.text) if _named(k) in ("before", "own_goal_before")]
            if earlier or _CREDIT_CHANGE.search(_own_words(sentence.text)):
                problems.append(
                    f"{part} sentence {i}: code ends the casual line with the change of credit ('{said}'), so"
                    " leave it out of your sentences"
                )
    return problems
