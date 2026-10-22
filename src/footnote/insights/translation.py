"""A card's wording in other languages, and the check that its figures and names came through.

The agents write English, as the templates do; Azure AI Translator renders it in Spanish and French
(footnote.agents.translator). A translator can translate a name that happens to be a word, read
"6'" as six feet, or drop a figure, so the text it's given is prepared first. Each name is a
dictionary entry that translates as itself: the name comes back as it is, and the sentence is still
built around it. (A name marked notranslate comes back too, but the Translator can't then build the
sentence: verbs are left in the infinitive.) Each minute is written out ("minute 6"), a word it has
got wrong is said another way ("spell" as "period"), and a headline
is given a full stop, so "Femi Adeyani scores" reads as a sentence and not as a name and a noun
("Femi Adeyani puntuaciones"); the stop is taken off the translation again. What comes back has the
Translator's known slips put right (`mend`): a word that is never the football one ("penalización"
for a penalty, "balonmano" for a handball) and a score line broken up ("0–1 para Saltmarsh y
Kingsferry") or read as one club's lead ("a favor de Saltmarsh 1–2 Kingsferry"). Code then holds
each translation to the English it came from: the same figures, every name, each score line whole,
nothing empty, no word twice in a row. A small number may come back as a word ("1 shot" as "un
tiro", "minute 2" as "el segundo minuto"), but no figure may change or appear. One that fails isn't
shown: the viewer reads the English (docs/audience.md, P2).
"""

from __future__ import annotations

import html
import re
from collections import Counter

from footnote.insights.facts import EN_DASH

LANGUAGES = ("es", "fr")
LANGUAGE_NAMES = {"es": "Spanish", "fr": "French"}
PARTS = ("headline", "casual", "analyst")

_ENTRY = re.compile(r'<mstrans:dictionary translation="[^"]*">(.*?)</mstrans:dictionary>', re.DOTALL)
# A minute as the cards write it: "23'", "90+2'".
_MINUTE = re.compile(r"(\d+(?:\+\d+)?)['’]")
# A figure as either language writes it: "89.1", or "89,1" with a decimal comma.
_FIGURE = re.compile(r"\d+(?:[.,]\d+)?")
_WORD = re.compile(r"\w+")
# A word twice in a row: "a été revu et déclaré déclaré hors-jeu". French repeats "nous" and "vous"
# in reflexive verbs ("nous nous sommes"), which is right.
_TWICE = re.compile(r"\b(?!(?:nous|vous)\b)([^\W\d_]+)\s+\1\b", re.IGNORECASE)
# English the Translator got wrong, or gave word for word, said another way, each with what came back.
_CLEARER = [
    # "hechizo" and "sort": a magic spell.
    (re.compile(r"\bspell(s?)\b"), r"period\1"),
    # "En la recta final" and "dans la ligne droite", the home straight, for "in the stretch".
    (re.compile(r"\b([Tt]he|[Tt]hat|[Tt]his|[Aa]|[Ee]ach) stretch\b"), r"\1 period"),
    # "Maintenu Kingsferry au sol" (held down on the ground) for "kept Kingsferry pinned for 61%";
    # "pinned in their own half" came back right and stays.
    (re.compile(r"\bpinned(?= for\b)"), "penned in"),
    # "La razón del técnico", "raison du joueur", "el asistente corrigió".
    (re.compile(r"\b([Tt]he) provider\b"), r"\1 data provider"),
    # "El disparo iba a darlo".
    (re.compile(r"\bwas on target\b"), "was heading into the goal"),
    # "Hors cible".
    (re.compile(r"\bwas off target\b"), "missed the goal"),
    # "VAR found no handball": "n'a pas obtenu de main", got no handball.
    (re.compile(r"\bfound no\b"), "saw no"),
    # "Tient toujours".
    (re.compile(r"\bdecision stands\b"), "decision is upheld"),
    # "Una posterior penalti" and "un penalty ultérieure" for "a later penalty check" (the check
    # dropped), "la prise de main" for "the handball check".
    (re.compile(r"\b(?:VAR's |VAR )?penalty check(s?)\b"), r"VAR check\1 for a penalty"),
    (re.compile(r"\b(?:VAR's |VAR )?(offside|handball) check(s?)\b"), r"VAR check\2 for \1"),
    # "Ninguna ofensa" and "aucune offense": an insult.
    (re.compile(r"\bno offence\b"), "no foul"),
    # "Une contre-action" for "a counter move".
    (re.compile(r"\bcounter move\b"), "counter-attack"),
    # "Une contre-prise" for "a counter finish", and "a late counter strike" as a counter-attack that
    # scored by itself ("un contragolpe tardío", "une contre-attaque tardive").
    (re.compile(r"\bcounter (strike|finish|goal|shot)\b"), r"\1 on the counter-attack"),
    # "Un contre-but" for "after a counter", "a frappé un contre" for "hit a counter". "On the counter"
    # stays: "broke on the counter-attack" came back as "a contre-attaqué en contre-attaque".
    (re.compile(r"\b([Aa]) counter\b(?!-)(?! move)"), r"\1 counter-attack"),
    # "Subissant une pression" (undergoing pressure) for "sustaining pressure".
    (re.compile(r"\bsustaining (?:the )?pressure\b"), "keeping up the pressure"),
    # "A concédé une concéderie" and "une place" for "conceded to Femi Adeyani".
    (re.compile(r"\bconceded to\b"), "conceded a goal to"),
    # "Ce qui a permis à Saltmarsh de rester 0–1 pour Kingsferry" for "so the score stayed Saltmarsh 0–1
    # Kingsferry", as the template's "The score is unchanged:" avoids.
    (
        re.compile(rf"\b([Tt])he score (?:stayed|remained) (?=(?:[^\s.;:]+ ){{1,3}}\d+{EN_DASH}\d+)"),
        r"\1he score was unchanged: ",
    ),
    (
        re.compile(rf"\b([Tt])he score (?:stays|remains|is still) (?=(?:[^\s.;:]+ ){{1,3}}\d+{EN_DASH}\d+)"),
        r"\1he score is unchanged: ",
    ),
    # "Su pase más largo" (their longest pass) and "traversée" for "their longest passage".
    (re.compile(r"\b([Ll]ongest|[Tt]heir|[Ii]ts) passage\b"), r"\1 sequence"),
    # "A quitté la botte".
    (re.compile(r"\bleft the boot\b"), "left the foot"),
    # "Hizo el último adelantamiento" (an overtaking) and "le dernier passage".
    (re.compile(r"\bmade the (?:last|final) pass\b"), "played the final pass"),
    # "La última bola" and "la dernière balle", a ball itself.
    (re.compile(r"\bthe (last|final) ball\b"), r"the \1 pass"),
    # "Ninguna de las partes", with "4 pasadas" after it.
    (re.compile(r"\b([Nn])either side\b"), r"\1either team"),
    # "Varlan levels for Saltmarsh": "sube nivel" and "monte".
    (re.compile(r"\blevels\b"), "equalises"),
    (re.compile(r"\blevelled\b"), "equalised"),
    # "En la cima" (at the summit), "en cabeza" and "en tête" (in the lead).
    (re.compile(r"\bon top of the (game|match)\b"), r"dominating the \1"),
    (re.compile(r"\bon top\b(?! of\b)"), "dominating"),
    # "Una carrera" and "une course", a run on foot, for "a run from 2' with 44 passes". A "run of
    # passes" came back right ("racha", "série") and stays.
    (re.compile(r"\b([Aa]|[Tt]he|[Tt]heir|[Ii]ts|longest) run\b(?! of\b)(?=[^.;:]*\bpasses\b)"), r"\1 sequence"),
    # "Largas carreras" and "longues courses" for "building long runs", with no passes after it.
    (re.compile(r"\b([Ll]ong|[Ll]onger) runs\b(?! of\b)"), r"\1 passing sequences"),
    # "En los minutos de la tarde": in the afternoon.
    (re.compile(r"\blate on\b"), "late in the match"),
    # "Originalmente llamado" and "initialement appelé" (originally called) for a goal "originally given
    # as Jory Penhallow". Before an own goal or a possessive it stays.
    (re.compile(r"\boriginally given as\b(?! an?\b)(?![^,.;)]*['’]s\b)"), "originally credited to"),
    # "Una jugada regular" (a mediocre move) and "une action de jeu normale".
    (re.compile(r"\b([Aa]) regular play\b"), r"\1n open play"),
    (re.compile(r"\bregular play\b"), "open play"),
    # "Bajo control y presión" and "sous contrôle et sous pression": under pressure, the wrong way round.
    (re.compile(r"\bin control and pressure\b"), "in control and pressing"),
    # "A largement contrôlé la seconde minute" (controlled the second minute) for "largely in control
    # from 2'".
    (re.compile(r"\bin control from\b"), "in control of the game from"),
    # "Saltmarsh empatar para poner el Saltmarsh 1–1 Kingsferry" (an infinitive, and no "marcador") for
    # "Saltmarsh equalise to make it Saltmarsh 1–1 Kingsferry".
    (re.compile(rf",? to make it(?= (?:[^\s.;:]+ ){{0,3}}\d+{EN_DASH}\d+)"), ", making it"),
    # "Entre el segundo y el minuto 17" (between them) for "spells from 2' and 17'".
    (re.compile(r"\bfrom minute (\d+(?:\+\d+)?) and minute (\d+(?:\+\d+)?)"), r"from minute \1 and from minute \2"),
]

# A headline said another way, the whole headline only: "Saltmarsh pinning Kingsferry back" came back
# as "Saltmarsh atrapa a Kingsferry" and, for the other club, "Kingsferry inmovilizando a Saltmarsh";
# "keep ... penned in" comes back the same way for both ("mantiene a ... acorralado"). An agent's
# "Saltmarsh pin Kingsferry back" came back as "Saltmarsh devuelve a Kingsferry" and "remet Kingsferry
# au sol", and "Femi Adeyani gives Kingsferry lead", without its article, as "donne la tête".
_HEADLINE_CLEARER = [
    (re.compile(r"^(.+) pinning (.+) back$"), r"\1 keep \2 penned in"),
    (re.compile(r"^(.+) pin (.+) back$"), r"\1 keep \2 penned in"),
    (re.compile(r"^(.+) pins (.+) back$"), r"\1 keeps \2 penned in"),
    (re.compile(r"^(.+) gives ([A-Z]\S*(?: [A-Z]\S*)?) lead$"), r"\1 gives \2 the lead"),
]

# Words the Translator gives that are never the football word, put right in its output: a penalty
# in a short headline came back as "penalización" and "pénalité" (a penalisation), though full
# sentences got "penalti" and "penalty"; a handball as "balonmano" and "handball" (the sport: French
# says "main"); and a pass as "pasada" and "passage". The article and adjective go with the noun, as
# each language needs.
_FOOTBALL_WORDS: dict[str, list[tuple[re.Pattern[str], str]]] = {
    "es": [
        (re.compile(pattern), right)
        for pattern, right in (
            (r"\bUna penalización\b", "Un penalti"),
            (r"\buna penalización\b", "un penalti"),
            (r"\bLa penalización\b", "El penalti"),
            (r"\bla penalización\b", "el penalti"),
            (r"\bLas penalizaciones\b", "Los penaltis"),
            (r"\blas penalizaciones\b", "los penaltis"),
            (r"\bPenalizaciones\b", "Penaltis"),
            (r"\bpenalizaciones\b", "penaltis"),
            (r"\bPenalización\b", "Penalti"),
            (r"\bpenalización\b", "penalti"),
            (r"\bEl balonmano\b", "La mano"),
            (r"\bel balonmano\b", "la mano"),
            (r"\bdel balonmano\b", "de la mano"),
            (r"\bUn balonmano\b", "Una mano"),
            (r"\bun balonmano\b", "una mano"),
            (r"\bBalonmano\b", "Mano"),
            (r"\bbalonmano\b", "mano"),
            (r"\bLa última pasada\b", "El último pase"),
            (r"\bla última pasada\b", "el último pase"),
            (r"\bUna pasada\b", "Un pase"),
            (r"\buna pasada\b", "un pase"),
            # "Mano de balón" for "handball", and "juego libre" for "open play".
            (r"\bmano de balón\b", "mano"),
            (r"\bjuego libre\b", "juego abierto"),
            (r"\bpasadas completadas\b", "pases completados"),
            (r"\b(\d+) pasadas seguidas\b", r"\1 pases seguidos"),
            (r"\b(\d+) pasadas\b", r"\1 pases"),
            (r"\bde pasadas\b", "de pases"),
            # "Superó las 4 pases" and "culminó una contraataque": both are masculine.
            (r"\b([Ll])as (\d+) pases\b", r"\1os \2 pases"),
            (r"\b([Uu])na contraataque\b", r"\1n contraataque"),
        )
    ],
    "fr": [
        (re.compile(pattern), right)
        for pattern, right in (
            (r"\bUne pénalité\b", "Un penalty"),
            (r"\bune pénalité\b", "un penalty"),
            (r"\bLa pénalité\b", "Le penalty"),
            (r"\bla pénalité\b", "le penalty"),
            (r"\bAucune pénalité\b", "Aucun penalty"),
            (r"\baucune pénalité\b", "aucun penalty"),
            (r"\bPénalités\b", "Penaltys"),
            (r"\bpénalités\b", "penaltys"),
            (r"\bPénalité\b", "Penalty"),
            (r"\bpénalité\b", "penalty"),
            (r"\bUn handball\b", "Une main"),
            (r"\bun handball\b", "une main"),
            (r"\bLe handball\b", "La main"),
            (r"\ble handball\b", "la main"),
            (r"\bdu handball\b", "de la main"),
            (r"\bHandball\b", "Main"),
            (r"\bhandball\b", "main"),
            (r"\bLe dernier passage\b", "La dernière passe"),
            (r"\ble dernier passage\b", "la dernière passe"),
            (r"\bdu dernier passage\b", "de la dernière passe"),
            (r"\bau dernier passage\b", "à la dernière passe"),
            (r"\bun dernier passage\b", "une dernière passe"),
            (r"\bpassages (?:achevés|complétés)\b", "passes complétées"),
            (r"\bpassages réussis\b", "passes réussies"),
            (r"\b(\d+) passages\b", r"\1 passes"),
            (r"\bde passages\b", "de passes"),
            # "Jeu libre" for "open play", which it also gives as "jeu ouvert".
            (r"\bjeu libre\b", "jeu ouvert"),
            # "A marqué sur un contre-attaque": the noun is feminine.
            (r"\b([Uu])n contre-attaque\b", r"\1ne contre-attaque"),
            (r"\bLe contre-attaque\b", "La contre-attaque"),
            (r"\ble contre-attaque\b", "la contre-attaque"),
            (r"\b([Dd])u contre-attaque\b", r"\1e la contre-attaque"),
            (r"\bAu contre-attaque\b", "À la contre-attaque"),
            (r"\bau contre-attaque\b", "à la contre-attaque"),
            (r"\b([Cc])e contre-attaque\b", r"\1ette contre-attaque"),
        )
    ],
}
# A score line the Translator broke up: a word put inside it ("Saltmarsh 1–1 en Kingsferry"), or the
# score put before the clubs ("0–1 para Saltmarsh y Kingsferry", "1–1 pour Saltmarsh Kingsferry").
_SCORE_WORD = r"(?:en|a|à|contre|contra|vs\.?|para|pour)"
_LINE = re.compile(rf"^(.+) (\d+{EN_DASH}\d+) (.+)$")
# "In favour of" before a whole score line, which reads as the first club's lead: "a favor de" and "en
# faveur de Saltmarsh 1–2 Kingsferry" for "turns the game to" and "takes the score to" that line. The
# "to" it was takes its place.
_IN_FAVOUR = {"es": (r"a favor del?", "a"), "fr": (r"en faveur d[eu]", "à")}

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
        **dict.fromkeys(("deux", "deuxième", "second", "seconde"), 2),
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
    texts = []
    for part in PARTS:
        text = card[part]
        if part == "headline":
            for wording, clearer in _HEADLINE_CLEARER:
                text = wording.sub(clearer, text)
        texts.append(protect(text + "." if _stops(part, text) else text, names))
    return texts


def read_back(card: dict[str, str], texts: list[str]) -> dict[str, str]:
    """The translator's texts for each part of the card, as plain text, any full stop added taken off."""
    out = {}
    for part, text in zip(PARTS, texts, strict=True):
        plain = unprotect(text)
        out[part] = plain.removesuffix(".") if _stops(part, card[part]) else plain
    return out


def mend(card: dict[str, str], translated: dict[str, str], names: list[str], lang: str) -> dict[str, str]:
    """The translation with the Translator's known slips put right: a word that is never the football
    one, and a score line the English has whole ("Saltmarsh 1–1 Kingsferry") that came back broken up
    or "in favour of"."""
    favour = _IN_FAVOUR.get(lang)
    out = {}
    for part in PARTS:
        text = translated.get(part, "")
        for wrong, right in _FOOTBALL_WORDS.get(lang, []):
            text = wrong.sub(right, text)
        for line in _score_lines(card.get(part, ""), names) if names else []:
            parts = _LINE.match(line)
            assert parts is not None  # a score line always has its score between two names
            home, score, away = (re.escape(p) for p in parts.groups())
            text = re.sub(rf"(?<![\w]){home} {score} {_SCORE_WORD} {away}(?![\w])", line, text)
            text = re.sub(rf"(?<![\w]){score} {_SCORE_WORD} {home} (?:y |et )?{away}(?![\w])", line, text)
            if favour:
                text = re.sub(rf"\b{favour[0]} (?={re.escape(line)}(?![\w]))", f"{favour[1]} ", text)
        out[part] = text
    return out


def _score_lines(text: str, names: list[str]) -> list[str]:
    """Each score line in a text, a name either side of the score: "Saltmarsh 1–1 Kingsferry"."""
    name = "|".join(re.escape(n) for n in names)
    return re.findall(rf"(?<![\w])(?:{name}) \d+{EN_DASH}\d+ (?:{name})(?![\w])", text)


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
        for line in _score_lines(source, names) if names else []:
            if line not in target:
                problems.append(f"{part}: the score line '{line}' is broken up in the translation")
        if (twice := _TWICE.search(target)) is not None and not _TWICE.search(source):
            problems.append(f"{part}: '{twice.group(0)}', a word twice in a row")
    return problems
