"""A card's wording in other languages, and the check that its figures and names came through.

The agents write English, as the templates do; Azure AI Translator renders it in Spanish and French
(footnote.agents.translator). A translator can drop a figure, reformat it into another one, or
translate a name that happens to be a word, so the names are marked for it to leave alone, and code
then holds each translation to the English it came from: the same figures, every name, nothing empty.
One that fails isn't shown: the viewer reads the English (docs/audience.md, P2).
"""

from __future__ import annotations

import html
import re

LANGUAGES = ("es", "fr")
LANGUAGE_NAMES = {"es": "Spanish", "fr": "French"}
PARTS = ("headline", "casual", "analyst")

_KEEP = '<span class="notranslate">'
_SPAN = re.compile(r'<span class="notranslate">(.*?)</span>', re.DOTALL)
# A figure as either language writes it: "89.1", or "89,1" with a decimal comma.
_FIGURE = re.compile(r"\d+(?:[.,]\d+)?")


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


def protect(text: str, names: list[str]) -> str:
    """The text as HTML for the translator, with each name marked to be left as it is."""
    escaped = html.escape(text, quote=False)
    if not names:
        return escaped
    return _pattern([html.escape(n, quote=False) for n in names]).sub(lambda m: f"{_KEEP}{m.group(1)}</span>", escaped)


def unprotect(text: str) -> str:
    """The translator's HTML back to plain text: the marks taken off, the escapes undone."""
    return html.unescape(_SPAN.sub(lambda m: m.group(1), text)).strip()


def figures(text: str) -> list[str]:
    """The figures in a text, in order of size, a decimal comma read as a point."""
    return sorted((f.replace(",", ".") for f in _FIGURE.findall(text)), key=lambda f: (float(f), f))


def check(english: dict[str, str], translated: dict[str, str], names: list[str]) -> list[str]:
    """What didn't come through from the English card into its translation, or nothing."""
    problems = []
    found = _pattern(names) if names else None
    for part in PARTS:
        source, target = english.get(part, ""), translated.get(part, "")
        if source.strip() and not target.strip():
            problems.append(f"{part}: the translation is empty")
            continue
        if figures(source) != figures(target):
            problems.append(f"{part}: the figures {figures(source)} came out as {figures(target)}")
        for name in sorted(set(found.findall(source))) if found else []:
            if name not in target:
                problems.append(f"{part}: '{name}' is missing from the translation")
    return problems
