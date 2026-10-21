"""Translating cards: names marked for the translator to keep, and the check that every figure and
name came through (footnote.insights.translation)."""

from __future__ import annotations

from footnote.insights.translation import check, figures, names_of, protect, unprotect
from footnote.live.match import load_match

NAMES = ["Femi Adeyani", "Kingsferry", "Saltmarsh", "Adeyani", "Varlan"]
CARD = {
    "headline": "Adeyani puts Kingsferry ahead",
    "casual": "Saltmarsh 0–1 Kingsferry: Femi Adeyani scores at 23' after Varlan's pass went astray.",
    "analyst": "The shot left the boot at 89.1 km/h; Saltmarsh had 71% of the ball.",
}


def test_names_are_marked_whole_and_come_back_plain() -> None:
    marked = protect("Femi Adeyani scores & Saltmarsh's Varlan watches", NAMES)
    assert marked == (
        '<span class="notranslate">Femi Adeyani</span> scores &amp; '
        '<span class="notranslate">Saltmarsh</span>\'s <span class="notranslate">Varlan</span> watches'
    )
    assert unprotect(marked) == "Femi Adeyani scores & Saltmarsh's Varlan watches"


def test_the_match_names_include_surnames_and_clubs_longest_first() -> None:
    names = names_of(load_match().meta)
    assert {"Femi Adeyani", "Adeyani", "Saltmarsh Rovers", "Saltmarsh", "Kingsferry"} <= set(names)
    assert names.index("Femi Adeyani") < names.index("Adeyani")


def test_figures_read_a_decimal_comma_as_a_point() -> None:
    assert figures("89,1 km/h, 71 % y 23'") == figures("89.1 km/h, 71% at 23'") == ["23", "71", "89.1"]


def test_a_faithful_translation_passes() -> None:
    spanish = {
        "headline": "Adeyani pone por delante a Kingsferry",
        "casual": "Saltmarsh 0–1 Kingsferry: Femi Adeyani marca en el 23' tras un pase errado de Varlan.",
        "analyst": "El disparo salió a 89,1 km/h; Saltmarsh tuvo el 71 % del balón.",
    }
    assert check(CARD, spanish, NAMES) == []


def test_a_lost_or_changed_figure_or_name_fails() -> None:
    lost = {**CARD, "analyst": "The shot left the boot quickly; Saltmarsh had 71% of the ball."}
    changed = {**CARD, "casual": CARD["casual"].replace("23'", "32'")}
    renamed = {**CARD, "headline": "Adeyani pone por delante a Ferry del Rey"}
    empty = {**CARD, "casual": " "}
    assert any("89.1" in p for p in check(CARD, lost, NAMES))
    assert any("figures" in p for p in check(CARD, changed, NAMES))
    assert check(CARD, renamed, NAMES) == ["headline: 'Kingsferry' is missing from the translation"]
    assert check(CARD, empty, NAMES) == ["casual: the translation is empty"]
