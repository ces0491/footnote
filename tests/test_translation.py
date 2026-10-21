"""Translating cards: the text prepared for the translator, and the check that every figure and name
came through (footnote.insights.translation)."""

from __future__ import annotations

from footnote.insights.translation import check, figures, names_of, prepare, protect, read_back, unprotect
from footnote.live.match import load_match

NAMES = ["Femi Adeyani", "Kingsferry", "Saltmarsh", "Adeyani", "Varlan"]
CARD = {
    "headline": "Adeyani puts Kingsferry ahead",
    "casual": "Saltmarsh 0–1 Kingsferry: Femi Adeyani scores at 23' after Varlan's pass went astray.",
    "analyst": "The shot left the boot at 89.1 km/h; Saltmarsh had 71% of the ball.",
}


def _entry(name: str) -> str:
    return f'<mstrans:dictionary translation="{name}">{name}</mstrans:dictionary>'


def test_names_become_dictionary_entries_and_minutes_are_written_out() -> None:
    marked = protect("Femi Adeyani scores at 90+2' & Saltmarsh's Varlan watches", NAMES)
    assert marked == (
        f"{_entry('Femi Adeyani')} scores at minute 90+2 &amp; {_entry('Saltmarsh')}'s {_entry('Varlan')} watches"
    )
    # The translator replaces each entry with its translation; one it left would come off.
    assert unprotect(marked) == "Femi Adeyani scores at minute 90+2 & Saltmarsh's Varlan watches"
    assert unprotect("El VAR revisa el gol de Femi Adeyani &amp; más") == "El VAR revisa el gol de Femi Adeyani & más"


def test_words_the_translator_gets_wrong_are_said_another_way() -> None:
    marked = protect("Long spells on top, then a spell under pressure. The provider's reason: a deflection.", [])
    assert marked == "Long periods on top, then a period under pressure. The data provider's reason: a deflection."
    assert protect("Later the provider corrected it; the data provider's reason stands.", []) == (
        "Later the data provider corrected it; the data provider's reason stands."
    )
    assert protect("Spellbrook was smoothed as tracking providers report it.", []) == (
        "Spellbrook was smoothed as tracking providers report it."
    )


def test_a_headline_goes_with_a_full_stop_that_comes_off_again() -> None:
    card = {"headline": "Femi Adeyani scores", "casual": "Saltmarsh 0–1 Kingsferry at 23'.", "analyst": ""}
    assert prepare(card, NAMES) == [
        f"{_entry('Femi Adeyani')} scores.",
        f"{_entry('Saltmarsh')} 0–1 {_entry('Kingsferry')} at minute 23.",
        "",
    ]
    back = read_back(card, ["Femi Adeyani anota.", "Saltmarsh 0–1 Kingsferry en el minuto 23.", ""])
    assert back == {
        "headline": "Femi Adeyani anota",
        "casual": "Saltmarsh 0–1 Kingsferry en el minuto 23.",
        "analyst": "",
    }
    # A headline with its own closing mark keeps it.
    asking = {**card, "headline": "Offside?"}
    assert prepare(asking, NAMES)[0] == "Offside?"
    assert read_back(asking, ["¿Fuera de juego?", "", ""])["headline"] == "¿Fuera de juego?"


def test_the_match_names_include_surnames_and_clubs_longest_first() -> None:
    names = names_of(load_match().meta)
    assert {"Femi Adeyani", "Adeyani", "Saltmarsh Rovers", "Saltmarsh", "Kingsferry"} <= set(names)
    assert names.index("Femi Adeyani") < names.index("Adeyani")


def test_figures_read_a_decimal_comma_as_a_point() -> None:
    assert figures("89,1 km/h, 71 % y 23'") == figures("89.1 km/h, 71% at 23'") == ["23", "71", "89.1"]


def test_a_faithful_translation_passes() -> None:
    spanish = {
        "headline": "Adeyani pone por delante a Kingsferry",
        "casual": "Saltmarsh 0–1 Kingsferry: Femi Adeyani marca en el minuto 23 tras un pase errado de Varlan.",
        "analyst": "El disparo salió a 89,1 km/h; Saltmarsh tuvo el 71 % del balón.",
    }
    assert check(CARD, spanish, NAMES, "es") == []


def test_a_small_number_may_come_back_as_a_word() -> None:
    english = {"casual": "Saltmarsh pressed from 2' and forced 1 shot in the 10 minutes after."}
    spanish = {"casual": "Saltmarsh presionó desde el segundo minuto y forzó un disparo en los 10 minutos siguientes."}
    french = {"casual": "Saltmarsh a pressé dès la 2e minute et a forcé un tir dans les dix minutes suivantes."}
    assert check(english, spanish, NAMES, "es") == []
    assert check(english, french, NAMES, "fr") == []
    # A figure that changed, or one the English doesn't have, still fails, words or not.
    changed = {"casual": "Saltmarsh presionó desde el segundo minuto y forzó un disparo en los 12 minutos siguientes."}
    added = {
        "casual": "Saltmarsh presionó desde el minuto 2 y forzó 1 disparo, a 1,80 m, en los 10 minutos siguientes."
    }
    assert check(english, changed, NAMES, "es") and check(english, added, NAMES, "es")
    # A figure missing with no word for it fails too.
    assert check({"casual": "Kingsferry had 3 shots."}, {"casual": "Kingsferry tuvo disparos."}, NAMES, "es")


def test_a_lost_or_changed_figure_or_name_fails() -> None:
    lost = {**CARD, "analyst": "The shot left the boot quickly; Saltmarsh had 71% of the ball."}
    changed = {**CARD, "casual": CARD["casual"].replace("23'", "32'")}
    renamed = {**CARD, "headline": "Adeyani pone por delante a Ferry del Rey"}
    empty = {**CARD, "casual": " "}
    assert any("89.1" in p for p in check(CARD, lost, NAMES, "es"))
    assert any("figures" in p for p in check(CARD, changed, NAMES, "es"))
    assert check(CARD, renamed, NAMES, "es") == ["headline: 'Kingsferry' is missing from the translation"]
    assert check(CARD, empty, NAMES, "es") == ["casual: the translation is empty"]
