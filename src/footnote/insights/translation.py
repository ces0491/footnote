"""A card's wording in other languages, and the check that its figures and names came through.

The agents write English, as the templates do; Azure AI Translator renders it in Spanish and French
(footnote.agents.translator). A translator can translate a name that happens to be a word, read
"6'" as six feet, or drop a figure, so the text it's given is prepared first. Each name is a
dictionary entry that translates as itself: the name comes back as it is, and the sentence is still
built around it. (A name marked notranslate comes back too, but the Translator can't then build the
sentence: verbs are left in the infinitive.) Each minute is written out ("minute 6"), a word it has
got wrong is replaced ("spell" by "period"), and a headline
is given a full stop, so "Femi Adeyani scores" reads as a sentence and not as a name and a noun
("Femi Adeyani puntuaciones"); the stop is taken off the translation again. Code then holds
each translation to the English it came from: the same figures, every name, nothing empty. A small
number may come back as a word ("1 shot" as "un tiro", "minute 2" as "el segundo minuto"), but no
figure may change or appear. One that fails isn't shown: the viewer reads the English
(docs/audience.md, P2).
"""

from __future__ import annotations

import html
import re
from collections import Counter

LANGUAGES = ("es", "fr")
LANGUAGE_NAMES = {"es": "Spanish", "fr": "French"}
PARTS = ("headline", "casual", "analyst")

_ENTRY = re.compile(r'<mstrans:dictionary translation="[^"]*">(.*?)</mstrans:dictionary>', re.DOTALL)
# A minute as the cards write it: "23'", "90+2'".
_MINUTE = re.compile(r"(\d+(?:\+\d+)?)['’]")
# A figure as either language writes it: "89.1", or "89,1" with a decimal comma.
_FIGURE = re.compile(r"\d+(?:[.,]\d+)?")
_WORD = re.compile(r"\w+")
# English the Translator got wrong, said another way: "spell" came back as "hechizo" and "sort" (a
# magic spell), "the provider's reason" as "la razón del técnico" and "raison du joueur", and "the
# provider corrected" as "el asistente corrigió".
_CLEARER = [
    (re.compile(r"\bspell(s?)\b"), r"period\1"),
    (re.compile(r"\b([Tt]he) provider\b"), r"\1 data provider"),
]

# The words a translation may use instead of a small number's figure, as a count or an ordinal.
NUMBER_WORDS: dict[str, dict[str, int]] = {
    "es": {
        **dict.fromkeys(("un", "uno", "una", "primer", "primero", "primera"), 1),
        **dict.fromkeys(("dos", "segundo", "segunda"), 2),
        **dict.fromkeys(("tres", "tercer", "tercero", "tercera"), 3),
        **dict.fromkeys(("cuatro", "cuarto", "cuarta"), 4),
        **dict.fromkeys(("cinco", "quinto", "quinta"), 5),
        **dict.fromkeys(("seis", "sexto", "sexta"), 6),
        **dict.fromkeys(("siete", "séptimo", "séptima"), 7),
        **dict.fromkeys(("ocho", "octavo", "octava"), 8),
        **dict.fromkeys(("nueve", "noveno", "novena"), 9),
        **dict.fromkeys(("diez", "décimo", "décima"), 10),
    },
    "fr": {
        **dict.fromkeys(("un", "une", "premier", "première"), 1),
        **dict.fromkeys(("deux", "deuxième"), 2),
        **dict.fromkeys(("trois", "troisième"), 3),
        **dict.fromkeys(("quatre", "quatrième"), 4),
        **dict.fromkeys(("cinq", "cinquième"), 5),
        **dict.fromkeys(("six", "sixième"), 6),
        **dict.fromkeys(("sept", "septième"), 7),
        **dict.fromkeys(("huit", "huitième"), 8),
        **dict.fromkeys(("neuf", "neuvième"), 9),
        **dict.fromkeys(("dix", "dixième"), 10),
    },
}


def names_of(meta: dict) -> list[str]:
    """Every name a card may carry for the match: each player's full name and surname, each club's
    name and short name. Longest first, so "Femi Adeyani" is marked whole before "Adeyani"."""
    names: set[str] = set()
    for club in (meta["home"], meta["away"]):
        names |= {club["name"], club["short_name"]}
    for lineup in meta["lineups"]:
        for player in [*lineup["starters"], *lineup["bench"]]:
            names |= {player["name"], player["name"].split()[-1]}
    return sorted(names, key=lambda n: (-len(n), n))


def _pattern(names: list[str]) -> re.Pattern[str]:
    return re.compile(r"(?<![\w])(" + "|".join(re.escape(n) for n in names) + r")(?![\w])")


def _entry(name: str) -> str:
    """A dictionary entry telling the translator the name translates as itself."""
    attribute = name.replace('"', "&quot;")
    return f'<mstrans:dictionary translation="{attribute}">{name}</mstrans:dictionary>'


def protect(text: str, names: list[str]) -> str:
    """The text as HTML for the translator: each minute written out, a word it gets wrong replaced,
    each name a dictionary entry."""
    text = _MINUTE.sub(r"minute \1", text)
    for word, clearer in _CLEARER:
        text = word.sub(clearer, text)
    escaped = html.escape(text, quote=False)
    if not names:
        return escaped
    return _pattern([html.escape(n, quote=False) for n in names]).sub(lambda m: _entry(m.group(1)), escaped)


def unprotect(text: str) -> str:
    """The translator's HTML back to plain text: any dictionary entry left taken off, the escapes undone."""
    return html.unescape(_ENTRY.sub(lambda m: m.group(1), text)).strip()


def _stops(part: str, text: str) -> bool:
    """Whether the part is given a full stop for the translator: a headline that ends without one."""
    return part == "headline" and bool(text.strip()) and text.rstrip()[-1] not in ".!?…"


def prepare(card: dict[str, str], names: list[str]) -> list[str]:
    """Each part of an English card, in PARTS order, as the translator is given it."""
    return [protect(card[part] + "." if _stops(part, card[part]) else card[part], names) for part in PARTS]


def read_back(card: dict[str, str], texts: list[str]) -> dict[str, str]:
    """The translator's texts for each part of the card, as plain text, any full stop added taken off."""
    out = {}
    for part, text in zip(PARTS, texts, strict=True):
        plain = unprotect(text)
        out[part] = plain.removesuffix(".") if _stops(part, card[part]) else plain
    return out


def figures(text: str) -> list[str]:
    """The figures in a text, in order of size, a decimal comma read as a point."""
    return sorted((f.replace(",", ".") for f in _FIGURE.findall(text)), key=lambda f: (float(f), f))


def _same_figures(source: str, target: str, lang: str) -> bool:
    """Every figure of the English is in the translation, a small one perhaps as a word, and no other."""
    expected, found = Counter(figures(source)), Counter(figures(target))
    if found - expected:
        return False
    vocabulary = NUMBER_WORDS.get(lang, {})
    words = Counter(n for w in _WORD.findall(target.lower()) if (n := vocabulary.get(w)))
    for figure, count in (expected - found).items():
        if not figure.isdigit() or words[int(figure)] < count:
            return False
        words[int(figure)] -= count
    return True


def check(english: dict[str, str], translated: dict[str, str], names: list[str], lang: str) -> list[str]:
    """What didn't come through from the English card into its translation, or nothing."""
    problems = []
    found = _pattern(names) if names else None
    for part in PARTS:
        source, target = english.get(part, ""), translated.get(part, "")
        if source.strip() and not target.strip():
            problems.append(f"{part}: the translation is empty")
            continue
        if not _same_figures(source, target, lang):
            problems.append(f"{part}: the figures {figures(source)} came out as {figures(target)}")
        for name in sorted(set(found.findall(source))) if found else []:
            if name not in target:
                problems.append(f"{part}: '{name}' is missing from the translation")
    return problems
