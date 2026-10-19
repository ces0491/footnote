"""Fictional names for players and officials.

Squads in the league are international, so names come from several "flavours",
each pairing common given names with invented surnames built from syllables.
Invented surnames keep accidental matches with real footballers rare; every
generated full name is still checked against Wikidata before it is used (see
scripts/check_names.py and data/name_check.json).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Flavour:
    key: str
    given: tuple[str, ...]
    prefixes: tuple[str, ...]
    suffixes: tuple[str, ...]


FLAVOURS: dict[str, Flavour] = {
    f.key: f
    for f in (
        Flavour(
            "english",
            (
                "Alfie",
                "Archie",
                "Ben",
                "Callum",
                "Charlie",
                "Dan",
                "Ellis",
                "Elliot",
                "Finley",
                "George",
                "Harvey",
                "Jack",
                "Jake",
                "Jamie",
                "Joe",
                "Kai",
                "Kit",
                "Leo",
                "Lewis",
                "Louie",
                "Max",
                "Nathan",
                "Ollie",
                "Reece",
                "Rhys",
                "Ryan",
                "Sam",
                "Toby",
                "Tom",
                "Zach",
            ),
            (
                "Ash",
                "Bram",
                "Carrow",
                "Fern",
                "Gall",
                "Hal",
                "Hollo",
                "Kell",
                "Lang",
                "Marr",
                "Nant",
                "Pell",
                "Pol",
                "Rad",
                "Rook",
                "Sel",
                "Tall",
                "Tre",
                "Wex",
                "Whin",
                "Yar",
                "Cobb",
                "Thack",
            ),
            (
                "ow",
                "wick",
                "by",
                "worth",
                "combe",
                "stone",
                "well",
                "den",
                "ridge",
                "field",
                "ett",
                "ard",
                "ington",
                "mere",
                "brook",
                "en",
                "ley",
                "sall",
            ),
        ),
        Flavour(
            "west_african",
            (
                "Tunde",
                "Kwame",
                "Kofi",
                "Emeka",
                "Chidi",
                "Seun",
                "Yaw",
                "Kunle",
                "Bayo",
                "Dayo",
                "Jide",
                "Kojo",
                "Sola",
                "Tobi",
                "Uche",
                "Ebuka",
                "Kelechi",
                "Nnamdi",
                "Yinka",
            ),
            ("Oke", "Ola", "Oye", "Aji", "Ilo", "Nwa", "Eze", "Oka", "Asa", "Ama", "Ogu", "Afo", "Obi"),
            ("wumi", "kanmi", "bode", "nde", "chukwu", "luwa", "meji", "sanya", "dipe", "toye", "nike", "fowe"),
        ),
        Flavour(
            "iberian",
            (
                "Mateo",
                "Diego",
                "Javi",
                "Rafael",
                "Iker",
                "Thiago",
                "Bruno",
                "Nico",
                "Pablo",
                "Sergio",
                "Hugo",
                "Andrés",
                "Joaquín",
                "Rodrigo",
                "Tiago",
                "Gonçalo",
                "Caio",
                "Davi",
                "Álvaro",
            ),
            ("Albar", "Cast", "Ferr", "Gall", "Mend", "Ortel", "Pazar", "Rive", "Salv", "Torr", "Bel", "Carv"),
            ("ano", "ella", "edo", "illa", "ondo", "eira", "ales", "ares", "anes", "ino", "osa", "ega", "ena"),
        ),
        Flavour(
            "balkan",
            (
                "Luka",
                "Nikola",
                "Ivan",
                "Andrej",
                "Filip",
                "Dario",
                "Matej",
                "Stefan",
                "Bojan",
                "Petar",
                "Toma",
                "Vuk",
                "Mihai",
                "Sorin",
                "Darius",
            ),
            ("Kos", "Mil", "Dra", "Vuk", "Jur", "Lov", "Kral", "Zel", "Bran", "Pet", "Hor", "Sav"),
            ("ović", "ić", "anić", "evski", "ek", "ac", "escu", "ean", "ar", "inek"),
        ),
        Flavour(
            "nordic",
            (
                "Jonas",
                "Lars",
                "Mikkel",
                "Sander",
                "Erik",
                "Henrik",
                "Niels",
                "Joost",
                "Daan",
                "Bram",
                "Timo",
                "Lukas",
                "Felix",
                "Emil",
                "Oskar",
                "Viktor",
                "Aksel",
            ),
            ("Holm", "Lind", "Dahl", "Strand", "Vos", "Kamp", "Haug", "Fjell", "Sund", "Wester", "Kloos", "Ekl"),
            ("gren", "stad", "vik", "ström", "berg", "man", "beek", "dijk", "sen", "strup", "by", "und"),
        ),
        Flavour(
            "french",
            (
                "Théo",
                "Mathis",
                "Bastien",
                "Yanis",
                "Enzo",
                "Noé",
                "Rayan",
                "Moussa",
                "Malik",
                "Sacha",
                "Adrien",
                "Lucas",
                "Maxime",
                "Corentin",
                "Ilyes",
                "Amine",
            ),
            ("Bel", "Char", "Brev", "Cass", "Gir", "Lam", "Mar", "Per", "Roch", "Val", "Duv", "Lef", "Mont"),
            ("ard", "ier", "eau", "ot", "ais", "elle", "ac", "ain", "et", "oux", "and"),
        ),
        Flavour(
            "irish_scottish",
            (
                "Cian",
                "Rory",
                "Callum",
                "Ewan",
                "Finn",
                "Lorcan",
                "Niall",
                "Ronan",
                "Cormac",
                "Kieran",
                "Declan",
                "Fraser",
                "Lachlan",
                "Euan",
            ),
            ("Mac", "Mc", "O'"),
            (
                "Ardle",
                "Callan",
                "Dowell",
                "Garrow",
                "Kerrin",
                "Lennan",
                "Morrow",
                "Tavish",
                "Quarrie",
                "Elhone",
                "Arran",
                "Bride",
                "Corran",
                "Fadyen",
                "Gilvray",
                "Ilwain",
                "Kinnell",
                "Laren",
                "Nair",
                "Tierne",
            ),
        ),
        Flavour(
            "east_asian",
            ("Kaito", "Ren", "Haruto", "Yuto", "Sota", "Daiki", "Min-jun", "Seo-jun", "Ji-ho", "Riku"),
            ("Kane", "Taki", "Mori", "Hase", "Ishi", "Yoshi", "Nakaz", "Sugi"),
            ("mura", "gawa", "zaki", "moto", "hara", "yama", "ta", "shima"),
        ),
    )
}

# Share of each flavour in a typical squad. Club-level variation is applied on top.
FLAVOUR_WEIGHTS: dict[str, float] = {
    "english": 0.34,
    "west_african": 0.13,
    "iberian": 0.13,
    "balkan": 0.08,
    "nordic": 0.10,
    "french": 0.11,
    "irish_scottish": 0.07,
    "east_asian": 0.04,
}


# Generated full names that turned out to belong to real people, found by scripts/check_names.py
# against Wikidata. The generator never uses them. Footballers are the reason for the check; other
# real people are blocked too, so no fictional player shares a name with anyone identifiable.
BLOCKED_NAMES: frozenset[str] = frozenset(
    {
        "Erik Lindberg",
        "Filip Kralevski",
        "Jonas Lindgren",
        "Kaito Sugizaki",
        "Lars Eklund",
        "Lars Lindström",
        "Nathan Ashley",
        "Oskar Eklund",
        "Oskar Sundman",
        "Ren Sugimoto",
        "Tiago Ferreira",
        "Viktor Lindgren",
    }
)


def _surname(flavour: Flavour, rng: np.random.Generator) -> str:
    prefix = flavour.prefixes[int(rng.integers(len(flavour.prefixes)))]
    # Resample suffixes that echo the end of the prefix ("Carrow" + "ow").
    while True:
        suffix = flavour.suffixes[int(rng.integers(len(flavour.suffixes)))]
        if not prefix.lower().endswith(suffix.lower()[:2]):
            break
    # Irish and Scottish prefixes join a capitalised stem as written ("McArdle", "O'Dowell").
    if prefix in ("Mac", "Mc", "O'"):
        return prefix + suffix
    # Drop a repeated letter at the join: "Ash" + "hallow" gives "Ashallow", not "Ashhallow".
    if prefix[-1].lower() == suffix[0].lower():
        suffix = suffix[1:]
    return prefix + suffix


def generate_name(flavour_key: str, rng: np.random.Generator) -> tuple[str, str]:
    """Return (given name, surname) for a flavour."""
    flavour = FLAVOURS[flavour_key]
    given = flavour.given[int(rng.integers(len(flavour.given)))]
    return given, _surname(flavour, rng)


def pick_flavour(rng: np.random.Generator, tilt: dict[str, float] | None = None) -> str:
    keys = list(FLAVOUR_WEIGHTS)
    weights = np.array([FLAVOUR_WEIGHTS[k] * (tilt or {}).get(k, 1.0) for k in keys])
    return keys[int(rng.choice(len(keys), p=weights / weights.sum()))]
