"""Translating cards: the text prepared for the translator, and the check that every figure and name
came through (footnote.insights.translation)."""

from __future__ import annotations

from footnote.insights.translation import check, figures, mend, names_of, prepare, protect, read_back, unprotect
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
    assert marked == (
        "Long periods dominating, then a period under pressure. The data provider's reason: a deflection."
    )
    assert protect("Later the provider corrected it; the data provider's reason stands.", []) == (
        "Later the data provider corrected it; the data provider's reason stands."
    )
    assert protect("Spellbrook was smoothed as tracking providers report it.", []) == (
        "Spellbrook was smoothed as tracking providers report it."
    )
    # "The shot was on target" came back as "el disparo iba a darlo"; shots on target stay as they are.
    assert protect("The shot was on target before the deflection, one of 5 shots on target.", []) == (
        "The shot was heading into the goal before the deflection, one of 5 shots on target."
    )
    assert protect("VAR found no handball, so the decision stands. The shot was off target.", []) == (
        "VAR saw no handball, so the decision is upheld. The shot missed the goal."
    )
    assert protect("It left the boot fast. Varlan made the last pass; Neither side has control.", []) == (
        "It left the foot fast. Varlan played the final pass; Neither team has control."
    )
    assert protect("Varlan levels, having levelled once: Saltmarsh on top, on top of the game.", []) == (
        "Varlan equalises, having equalised once: Saltmarsh dominating, dominating the game."
    )
    # A run of passes said so it isn't a run on foot; "a run of passes" and the run of play stay.
    assert protect("A run from 2' with 44 passes; their longest run was 20 passes.", []) == (
        "A sequence from minute 2 with 44 passes; their longest sequence was 20 passes."
    )
    assert protect("A run of 7 passes against the run of play.", []) == "A run of 7 passes against the run of play."
    assert protect("Saltmarsh built long runs, and long runs of possession.", []) == (
        "Saltmarsh built long passing sequences, and long runs of possession."
    )
    assert protect("Spells from 2' and 17'.", []) == "Spells from minute 2 and from minute 17."
    assert protect("Ferrano provided the final ball.", []) == "Ferrano provided the final pass."
    assert protect("Their longest sequence in the stretch; Saltmarsh stretch it.", []) == (
        "Their longest sequence in the period; Saltmarsh stretch it."
    )
    assert protect("Kept pinned for 61%, then pinned in their own half.", []) == (
        "Kept penned in for 61%, then pinned in their own half."
    )
    assert protect("A later penalty check, VAR's offside check and the handball check saw no offence.", []) == (
        "A later VAR check for a penalty, VAR check for offside and the VAR check for handball saw no foul."
    )
    assert protect("Adeyani finished a counter move.", []) == "Adeyani finished a counter-attack."
    assert protect("Their longest passage was 20 passes; a passage of play.", []) == (
        "Their longest sequence was 20 passes; a passage of play."
    )
    assert protect("No penalty late on, after a regular play move; regular play resumed.", []) == (
        "No penalty late in the match, after an open play move; open play resumed."
    )
    assert protect("Saltmarsh, in control and pressure, were in control from 2'.", []) == (
        "Saltmarsh, in control and pressing, were in control of the game from minute 2."
    )
    # Only before a score.
    assert protect("Saltmarsh equalise to make it Saltmarsh 1–1 Kingsferry, enough to make it count.", []) == (
        "Saltmarsh equalise, making it Saltmarsh 1–1 Kingsferry, enough to make it count."
    )
    # The old credit as a name; before an own goal or a possessive it stays.
    assert protect("Credited to Adeyani (originally given as Jory Penhallow).", []) == (
        "Credited to Adeyani (originally credited to Jory Penhallow)."
    )
    kept = "It was originally given as an own goal, originally given as Penhallow's own goal."
    assert protect(kept, []) == kept


def test_the_translators_known_slips_are_put_right() -> None:
    card = {"headline": "VAR: No penalty", "casual": "The score stays Saltmarsh 1–1 Kingsferry.", "analyst": "x"}
    spanish = {
        "headline": "VAR: Sin penalización",
        "casual": "El marcador sigue Saltmarsh 1–1 en Kingsferry.",
        "analyst": "x",
    }
    assert mend(card, spanish, NAMES, "es") == {
        "headline": "VAR: Sin penalti",
        "casual": "El marcador sigue Saltmarsh 1–1 Kingsferry.",
        "analyst": "x",
    }
    french = {
        "headline": "Pénalité pour Saltmarsh",
        "casual": "La VAR a vu une pénalité, à Saltmarsh 1–1 contre Kingsferry.",
        "analyst": "x",
    }
    assert mend(card, french, NAMES, "fr") == {
        "headline": "Penalty pour Saltmarsh",
        "casual": "La VAR a vu un penalty, à Saltmarsh 1–1 Kingsferry.",
        "analyst": "x",
    }
    # A score put before the clubs goes back between them.
    for broken, lang in (
        ("El marcador se mantiene 1–1 para Saltmarsh y Kingsferry.", "es"),
        ("Le score reste 1–1 pour Saltmarsh Kingsferry.", "fr"),
    ):
        assert "Saltmarsh 1–1 Kingsferry" in mend(card, {**card, "casual": broken}, NAMES, lang)["casual"]
    # A word next to a score the English doesn't have whole stays: "won 2–1 at Kingsferry".
    away = {"headline": "", "casual": "Saltmarsh won 2–1 at Kingsferry.", "analyst": ""}
    assert mend(away, {**away, "casual": "Saltmarsh ganó 2–1 en Kingsferry."}, NAMES, "es")["casual"] == (
        "Saltmarsh ganó 2–1 en Kingsferry."
    )
    # A handball is never the sport, and a pass never a "pasada".
    handball = {"headline": "VAR check: handball", "casual": "The goal is ruled out for handball.", "analyst": ""}
    assert mend(
        handball,
        {
            "headline": "Comprobación VAR: balonmano",
            "casual": "El gol queda anulado por balonmano. Varlan realizó la última pasada, una pasada de 4 pasadas.",
            "analyst": "",
        },
        NAMES,
        "es",
    ) == {
        "headline": "Comprobación VAR: mano",
        "casual": "El gol queda anulado por mano. Varlan realizó el último pase, un pase de 4 pases.",
        "analyst": "",
    }
    assert mend(
        handball,
        {"headline": "Contrôle VAR : handball", "casual": "Le but est annulé pour un handball.", "analyst": ""},
        NAMES,
        "fr",
    ) == {"headline": "Contrôle VAR : main", "casual": "Le but est annulé pour une main.", "analyst": ""}
    passes = {"headline": "", "casual": "Their longest sequence of completed passes was 7 passes.", "analyst": ""}
    assert mend(
        passes,
        {**passes, "casual": "La secuencia más larga de pasadas completadas fue de 7 pasadas."},
        NAMES,
        "es",
    )["casual"] == ("La secuencia más larga de pases completados fue de 7 pases.")
    loose = {**passes, "casual": "Desde juego libre, no vio mano de balón. Superó las 4 pases en una contraataque."}
    assert mend(passes, loose, NAMES, "es")["casual"] == (
        "Desde juego abierto, no vio mano. Superó los 4 pases en un contraataque."
    )
    assert mend(
        passes,
        {**passes, "casual": "Fut de 20 passages, de passages achevés ; Varlan a joué le dernier passage."},
        NAMES,
        "fr",
    )["casual"] == ("Fut de 20 passes, de passes complétées ; Varlan a joué la dernière passe.")
    # Open play as the Translator gives it elsewhere, and a counter-attack, which is feminine.
    countered = "Varlan a égalisé en jeu libre. Adeyani a marqué sur un contre-attaque, au bout du contre-attaque."
    assert mend(passes, {**passes, "casual": countered}, NAMES, "fr")["casual"] == (
        "Varlan a égalisé en jeu ouvert. Adeyani a marqué sur une contre-attaque, au bout de la contre-attaque."
    )
    assert mend(passes, {**passes, "casual": "Le contre-attaque, puis des contre-attaques."}, NAMES, "fr")[
        "casual"
    ] == ("La contre-attaque, puis des contre-attaques.")
    # "In favour of" before a whole score line was "to" it; before a club it stays.
    turned = {"headline": "", "casual": "Femi Adeyani turns the game to Saltmarsh 1–2 Kingsferry.", "analyst": ""}
    for favour, to, lang in (
        ("cambió el partido a favor de", "cambió el partido a", "es"),
        ("renverse le score en faveur de", "renverse le score à", "fr"),
    ):
        favoured = {**turned, "casual": f"Femi Adeyani {favour} Saltmarsh 1–2 Kingsferry."}
        assert mend(turned, favoured, NAMES, lang)["casual"] == f"Femi Adeyani {to} Saltmarsh 1–2 Kingsferry."
    club = {**turned, "casual": "Femi Adeyani cambió el partido a favor de Kingsferry: Saltmarsh 1–2 Kingsferry."}
    assert mend(turned, club, NAMES, "es") == club


def test_a_score_line_must_come_through_whole() -> None:
    english = {"headline": "", "casual": "The score is unchanged: Saltmarsh 1–1 Kingsferry.", "analyst": ""}
    kept = {**english, "casual": "El marcador no ha cambiado: Saltmarsh 1–1 Kingsferry."}
    assert check(english, kept, NAMES, "es") == []
    # Same figures and names, but read as a score for both clubs.
    broken = {**english, "casual": "Le score reste 1–1 pour Saltmarsh Kingsferry."}
    assert check(english, broken, NAMES, "fr") == [
        "casual: the score line 'Saltmarsh 1–1 Kingsferry' is broken up in the translation"
    ]


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
    # The pressure headline goes as "keep ... penned in", which comes back the same for either club;
    # the same words in a sentence stay.
    pinned = {**card, "headline": "Saltmarsh pinning Kingsferry back", "analyst": "Spent pinning Kingsferry back."}
    assert prepare(pinned, NAMES)[0] == f"{_entry('Saltmarsh')} keep {_entry('Kingsferry')} penned in."
    assert prepare(pinned, NAMES)[2] == f"Spent pinning {_entry('Kingsferry')} back."
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
    assert check(english, {"casual": french["casual"].replace("2e", "seconde")}, NAMES, "fr") == []
    # A figure that changed, or one the English doesn't have, still fails, words or not.
    changed = {"casual": "Saltmarsh presionó desde el segundo minuto y forzó un disparo en los 12 minutos siguientes."}
    added = {
        "casual": "Saltmarsh presionó desde el minuto 2 y forzó 1 disparo, a 1,80 m, en los 10 minutos siguientes."
    }
    assert check(english, changed, NAMES, "es") and check(english, added, NAMES, "es")
    # A figure missing with no word for it fails too.
    assert check({"casual": "Kingsferry had 3 shots."}, {"casual": "Kingsferry tuvo disparos."}, NAMES, "es")


def test_a_word_twice_in_a_row_fails_unless_the_english_has_it() -> None:
    english = {"casual": "The goal was reviewed and ruled out for offside."}
    garbled = {"casual": "Le but a été revu et déclaré déclaré hors-jeu."}
    assert check(english, garbled, NAMES, "fr") == ["casual: 'déclaré déclaré', a word twice in a row"]
    reflexive = {"casual": "Nous nous sommes trompés : le but a été annulé pour hors-jeu."}
    assert check(english, reflexive, NAMES, "fr") == []


def test_a_lost_or_changed_figure_or_name_fails() -> None:
    lost = {**CARD, "analyst": "The shot left the boot quickly; Saltmarsh had 71% of the ball."}
    changed = {**CARD, "casual": CARD["casual"].replace("23'", "32'")}
    renamed = {**CARD, "headline": "Adeyani pone por delante a Ferry del Rey"}
    empty = {**CARD, "casual": " "}
    assert any("89.1" in p for p in check(CARD, lost, NAMES, "es"))
    assert any("figures" in p for p in check(CARD, changed, NAMES, "es"))
    assert check(CARD, renamed, NAMES, "es") == ["headline: 'Kingsferry' is missing from the translation"]
    assert check(CARD, empty, NAMES, "es") == ["casual: the translation is empty"]
