"""The fictional league: clubs, team styles, strengths and squads.

Public information (names, shirt numbers, positions, heights, preferred foot,
formations, colours) goes into the feed's match metadata. Team styles, club
quality and player attributes are hidden: they drive the simulation and are
written only to the answer key.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from footnote.generator.formations import FORMATIONS, ROLE_FIT
from footnote.generator.names import BLOCKED_NAMES, generate_name, pick_flavour
from footnote.generator.rng import make_rng

STYLE_KEYS = (
    "possession",  # patience and retention when in possession
    "directness",  # preference for progressing the ball quickly and forwards
    "press",  # pressing intensity without the ball
    "line",  # defensive line height
    "width",  # use of the flanks and crossing
    "tempo",  # speed of ball circulation
    "counter",  # appetite for breaking quickly after a regain
    "aerial",  # long balls and aerial play
    "aggression",  # duel intensity, which drives fouls
)

# Archetype centres. Each club's style is its archetype plus seeded jitter.
ARCHETYPES: dict[str, dict[str, float]] = {
    "possession_press": dict(
        possession=0.78,
        directness=0.35,
        press=0.82,
        line=0.80,
        width=0.60,
        tempo=0.60,
        counter=0.40,
        aerial=0.20,
        aggression=0.50,
    ),
    "high_tempo_press": dict(
        possession=0.55,
        directness=0.65,
        press=0.92,
        line=0.72,
        width=0.55,
        tempo=0.88,
        counter=0.75,
        aerial=0.35,
        aggression=0.65,
    ),
    "balanced": dict(
        possession=0.50,
        directness=0.50,
        press=0.50,
        line=0.50,
        width=0.50,
        tempo=0.50,
        counter=0.50,
        aerial=0.45,
        aggression=0.50,
    ),
    "patient_mid_block": dict(
        possession=0.62,
        directness=0.40,
        press=0.40,
        line=0.50,
        width=0.50,
        tempo=0.42,
        counter=0.40,
        aerial=0.30,
        aggression=0.45,
    ),
    "low_block_counter": dict(
        possession=0.36,
        directness=0.66,
        press=0.36,
        line=0.32,
        width=0.50,
        tempo=0.65,
        counter=0.90,
        aerial=0.50,
        aggression=0.60,
    ),
    "wing_crossing": dict(
        possession=0.48,
        directness=0.52,
        press=0.50,
        line=0.50,
        width=0.90,
        tempo=0.50,
        counter=0.50,
        aerial=0.65,
        aggression=0.50,
    ),
    "direct_aerial": dict(
        possession=0.38,
        directness=0.78,
        press=0.50,
        line=0.45,
        width=0.65,
        tempo=0.55,
        counter=0.50,
        aerial=0.90,
        aggression=0.70,
    ),
}

ARCHETYPE_FORMATION = {
    "possession_press": "4-3-3",
    "high_tempo_press": "4-3-3",
    "balanced": "4-2-3-1",
    "patient_mid_block": "4-2-3-1",
    "low_block_counter": "4-4-2",
    "wing_crossing": "4-4-2",
    "direct_aerial": "4-4-2",
}


@dataclass(frozen=True)
class ClubSpec:
    """Fixed club identity. Quality is the club's latent strength on a 0-1 scale."""

    code: str
    name: str
    short_name: str
    ground: str
    colours: tuple[str, str]
    archetype: str
    quality: float
    formation: str | None = None


# The league. Names are invented and checked against real clubs (data/name_check.json).
# Quality spreads from title contenders to relegation candidates.
CLUB_SPECS: tuple[ClubSpec, ...] = (
    ClubSpec(
        "SAL",
        "Saltmarsh Rovers",
        "Saltmarsh",
        "The Saltings",
        ("#1F7A6D", "#F4F1E8"),
        "possession_press",
        0.74,
        "4-2-3-1",
    ),
    ClubSpec(
        "KIN", "Kingsferry Athletic", "Kingsferry", "Ferryside Road", ("#1B2A4A", "#E8A33D"), "low_block_counter", 0.57
    ),
    ClubSpec("ESK", "Eskerby Albion", "Eskerby", "Albion Fields", ("#C8102E", "#FFFFFF"), "possession_press", 0.82),
    ClubSpec("BRW", "Brackwater City", "Brackwater", "Weir Park", ("#6CABDD", "#1C2C5B"), "high_tempo_press", 0.78),
    ClubSpec("MAR", "Marrowby City", "Marrowby", "Marrowby Stadium", ("#5B2C83", "#F2C14E"), "possession_press", 0.68),
    ClubSpec("ASH", "Ashenford Town", "Ashenford", "Cinder Lane", ("#2E3A87", "#FFFFFF"), "balanced", 0.63),
    ClubSpec("LAR", "Larkmoor United", "Larkmoor", "Moorside", ("#E35205", "#0F0F0F"), "high_tempo_press", 0.60),
    ClubSpec("CAL", "Callowmere United", "Callowmere", "Mere Road", ("#7A263A", "#97C1E7"), "patient_mid_block", 0.58),
    ClubSpec(
        "DUN", "Dunmarrow Rangers", "Dunmarrow", "Rangers Ground", ("#00594F", "#F0E442"), "balanced", 0.55, "3-4-3"
    ),
    ClubSpec(
        "VEL",
        "Vellacott United",
        "Vellacott",
        "The Orchard",
        ("#B5121B", "#2B2B2B"),
        "patient_mid_block",
        0.52,
        "3-4-3",
    ),
    ClubSpec(
        "FAL", "Fallowmouth Wanderers", "Fallowmouth", "Harbour Park", ("#F7D117", "#1D428A"), "wing_crossing", 0.50
    ),
    ClubSpec("WRE", "Wrenmouth Town", "Wrenmouth", "Saltgate", ("#003DA5", "#F5F5F5"), "high_tempo_press", 0.50),
    ClubSpec("NET", "Netherwold County", "Netherwold", "County Ground", ("#3F7F3F", "#FFFFFF"), "balanced", 0.48),
    ClubSpec("KES", "Kestlebury Town", "Kestlebury", "Kestle Park", ("#D71920", "#FFD200"), "wing_crossing", 0.47),
    ClubSpec("ORR", "Orrinsford", "Orrinsford", "Millbank", ("#4B4B4B", "#E4002B"), "patient_mid_block", 0.46),
    ClubSpec("PEL", "Pellingham Borough", "Pellingham", "Borough Road", ("#8A1538", "#87CEEB"), "balanced", 0.44),
    ClubSpec("IRO", "Ironhithe Athletic", "Ironhithe", "The Hithe", ("#2F2F2F", "#C5A572"), "low_block_counter", 0.42),
    ClubSpec("YAR", "Yarrowfield City", "Yarrowfield", "Yarrow Park", ("#0072CE", "#FFB81C"), "wing_crossing", 0.40),
    ClubSpec("THI", "Thistlecombe", "Thistlecombe", "Combe Lane", ("#6A2C91", "#A2D45E"), "direct_aerial", 0.38),
    ClubSpec(
        "STE", "Stellhaven Harriers", "Stellhaven", "Haven Park", ("#00205B", "#E4E4E4"), "low_block_counter", 0.36
    ),
)

# Named players fixed by docs/experience.md. Attributes listed here override the generated ones.
CAST: dict[str, list[dict]] = {
    "SAL": [
        dict(
            given="Teo",
            surname="Varlan",
            shirt=10,
            role="AM",
            foot="R",
            height=177,
            attrs=dict(passing=0.90, vision=0.92, first_touch=0.86, dribbling=0.78, long_shots=0.86, composure=0.82),
        ),
        dict(
            given="Marco",
            surname="Dellow",
            shirt=9,
            role="ST",
            foot="R",
            height=184,
            attrs=dict(finishing=0.84, heading=0.74, first_touch=0.74, composure=0.76),
        ),
        dict(
            given="Jory",
            surname="Penhallow",
            shirt=4,
            role="CB",
            foot="R",
            height=189,
            attrs=dict(heading=0.80, tackling=0.76, marking=0.74),
        ),
    ],
    "KIN": [
        dict(
            given="Femi",
            surname="Adeyani",
            shirt=7,
            role="RW",
            foot="L",
            height=176,
            attrs=dict(top_speed=9.75, dribbling=0.84, finishing=0.70, first_touch=0.74, composure=0.70),
        ),
        dict(
            given="Isaac",
            surname="Brennholt",
            shirt=1,
            role="GK",
            foot="R",
            height=192,
            attrs=dict(gk_skill=0.76, handling=0.74),
        ),
    ],
}

SQUAD_ROLES = (
    "GK",
    "GK",
    "GK",
    "CB",
    "CB",
    "CB",
    "CB",
    "RB",
    "RB",
    "LB",
    "LB",
    "DM",
    "DM",
    "CM",
    "CM",
    "CM",
    "AM",
    "AM",
    "RW",
    "RW",
    "LW",
    "LW",
    "ST",
    "ST",
    "ST",
)

FIRST_CHOICE_NUMBER = {"GK": 1, "RB": 2, "LB": 3, "CB": 4, "DM": 6, "RW": 7, "CM": 8, "ST": 9, "AM": 10, "LW": 11}

# Role-typical attribute centres on a 0-1 scale (physical ones in units), before club quality.
ROLE_ATTRS: dict[str, dict[str, float]] = {
    "GK": dict(
        passing=0.45,
        vision=0.40,
        first_touch=0.45,
        dribbling=0.20,
        finishing=0.05,
        long_shots=0.05,
        heading=0.30,
        tackling=0.20,
        marking=0.30,
        top_speed=7.7,
        height=190,
    ),
    "CB": dict(
        passing=0.56,
        vision=0.46,
        first_touch=0.55,
        dribbling=0.38,
        finishing=0.30,
        long_shots=0.28,
        heading=0.74,
        tackling=0.72,
        marking=0.72,
        top_speed=8.9,
        height=188,
    ),
    "RB": dict(
        passing=0.58,
        vision=0.50,
        first_touch=0.60,
        dribbling=0.56,
        finishing=0.33,
        long_shots=0.38,
        heading=0.50,
        tackling=0.63,
        marking=0.61,
        top_speed=9.3,
        height=178,
    ),
    "LB": dict(
        passing=0.58,
        vision=0.50,
        first_touch=0.60,
        dribbling=0.56,
        finishing=0.33,
        long_shots=0.38,
        heading=0.50,
        tackling=0.63,
        marking=0.61,
        top_speed=9.3,
        height=178,
    ),
    "DM": dict(
        passing=0.66,
        vision=0.60,
        first_touch=0.64,
        dribbling=0.50,
        finishing=0.38,
        long_shots=0.50,
        heading=0.60,
        tackling=0.68,
        marking=0.65,
        top_speed=8.9,
        height=182,
    ),
    "CM": dict(
        passing=0.68,
        vision=0.64,
        first_touch=0.66,
        dribbling=0.58,
        finishing=0.45,
        long_shots=0.53,
        heading=0.50,
        tackling=0.56,
        marking=0.53,
        top_speed=9.0,
        height=179,
    ),
    "AM": dict(
        passing=0.70,
        vision=0.70,
        first_touch=0.70,
        dribbling=0.68,
        finishing=0.56,
        long_shots=0.60,
        heading=0.42,
        tackling=0.38,
        marking=0.40,
        top_speed=9.1,
        height=176,
    ),
    "RW": dict(
        passing=0.60,
        vision=0.58,
        first_touch=0.66,
        dribbling=0.72,
        finishing=0.58,
        long_shots=0.52,
        heading=0.40,
        tackling=0.35,
        marking=0.38,
        top_speed=9.5,
        height=175,
    ),
    "LW": dict(
        passing=0.60,
        vision=0.58,
        first_touch=0.66,
        dribbling=0.72,
        finishing=0.58,
        long_shots=0.52,
        heading=0.40,
        tackling=0.35,
        marking=0.38,
        top_speed=9.5,
        height=175,
    ),
    "ST": dict(
        passing=0.55,
        vision=0.52,
        first_touch=0.64,
        dribbling=0.60,
        finishing=0.70,
        long_shots=0.55,
        heading=0.66,
        tackling=0.30,
        marking=0.30,
        top_speed=9.3,
        height=183,
    ),
}

SKILL_KEYS = (
    "passing",
    "vision",
    "first_touch",
    "dribbling",
    "finishing",
    "long_shots",
    "heading",
    "tackling",
    "marking",
    "composure",
    "aggression",
    "discipline",
    "stamina",
    "gk_skill",
    "handling",
)


@dataclass
class Player:
    id: str
    club: str
    given: str
    surname: str
    shirt: int
    role: str
    foot: str
    height: int
    attrs: dict[str, float]
    # Named cast members start whenever they are available.
    first_choice: bool = False

    @property
    def name(self) -> str:
        return f"{self.given} {self.surname}"

    def public(self) -> dict:
        return dict(
            id=self.id,
            club=self.club,
            name=self.name,
            given=self.given,
            surname=self.surname,
            shirt=self.shirt,
            position=self.role,
            foot=self.foot,
            height_cm=self.height,
        )


@dataclass
class Club:
    spec: ClubSpec
    style: dict[str, float]
    formation: str
    squad: list[Player] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.spec.code.lower()

    @property
    def quality(self) -> float:
        return self.spec.quality

    def public(self) -> dict:
        s = self.spec
        return dict(
            id=self.id,
            code=s.code,
            name=s.name,
            short_name=s.short_name,
            ground=s.ground,
            colours=list(s.colours),
            formation=self.formation,
            squad=[p.public() for p in sorted(self.squad, key=lambda p: p.shirt)],
        )

    def hidden(self) -> dict:
        return dict(
            id=self.id,
            quality=self.quality,
            archetype=self.spec.archetype,
            style=self.style,
            players={p.id: p.attrs for p in self.squad},
        )


@dataclass
class Official:
    id: str
    name: str


@dataclass
class League:
    seed: int
    name: str
    season: str
    clubs: list[Club]
    referees: list[Official]

    def club(self, code_or_id: str) -> Club:
        key = code_or_id.lower()
        for c in self.clubs:
            if c.id == key:
                return c
        raise KeyError(code_or_id)

    def player(self, player_id: str) -> Player:
        for c in self.clubs:
            for p in c.squad:
                if p.id == player_id:
                    return p
        raise KeyError(player_id)

    def public(self) -> dict:
        return dict(
            name=self.name,
            season=self.season,
            clubs=[c.public() for c in self.clubs],
            referees=[dict(id=r.id, name=r.name) for r in self.referees],
        )

    def hidden(self) -> dict:
        return dict(seed=self.seed, clubs=[c.hidden() for c in self.clubs])

    def all_names(self) -> list[tuple[str, str]]:
        """Every person and club name in the league, as (kind, name)."""
        out = [("club", c.spec.name) for c in self.clubs]
        out += [("player", p.name) for c in self.clubs for p in c.squad]
        out += [("official", r.name) for r in self.referees]
        return out


LEAGUE_NAME = "Footnote League"
SEASON = "2026/27"
N_REFEREES = 12


def _style_for(spec: ClubSpec, rng: np.random.Generator) -> dict[str, float]:
    base = ARCHETYPES[spec.archetype]
    return {k: float(np.clip(base[k] + rng.normal(0.0, 0.06), 0.05, 0.95)) for k in STYLE_KEYS}


def _attrs_for(role: str, quality: float, rng: np.random.Generator) -> dict[str, float]:
    centre = ROLE_ATTRS[role]
    shift = (quality - 0.55) * 0.25
    a: dict[str, float] = {}
    for k in (
        "passing",
        "vision",
        "first_touch",
        "dribbling",
        "finishing",
        "long_shots",
        "heading",
        "tackling",
        "marking",
    ):
        a[k] = float(np.clip(centre[k] + shift + rng.normal(0, 0.07), 0.05, 0.97))
    a["composure"] = float(np.clip(0.55 + shift + rng.normal(0, 0.08), 0.1, 0.95))
    a["aggression"] = float(np.clip((0.6 if role in ("CB", "DM") else 0.5) + rng.normal(0, 0.1), 0.1, 0.95))
    a["discipline"] = float(np.clip(0.55 + rng.normal(0, 0.12), 0.1, 0.95))
    a["stamina"] = float(np.clip((0.72 if role in ("RB", "LB", "CM", "DM") else 0.62) + rng.normal(0, 0.08), 0.3, 0.97))
    a["top_speed"] = float(np.clip(centre["top_speed"] + 0.4 * (quality - 0.55) + rng.normal(0, 0.35), 7.0, 10.1))
    a["accel"] = float(np.clip(3.4 + rng.normal(0, 0.3), 2.6, 4.3))
    if role == "GK":
        a["gk_skill"] = float(np.clip(0.62 + shift + rng.normal(0, 0.07), 0.3, 0.95))
        a["handling"] = float(np.clip(0.62 + shift + rng.normal(0, 0.07), 0.3, 0.95))
    else:
        a["gk_skill"] = 0.05
        a["handling"] = 0.05
    return a


def _build_squad(
    club: Club, rng: np.random.Generator, name_rng: np.random.Generator, used_names: set[str], used_surnames: set[str]
) -> None:
    """Generate a 25-player squad. Surnames are unique across the league, share no three-letter
    stem within a squad, and never share a four-letter stem with a named cast member anywhere."""
    spec = club.spec
    cast_stems = {e["surname"][:4].lower() for entries in CAST.values() for e in entries}
    cast_queue: dict[str, list[dict]] = {}
    for cast_entry in CAST.get(spec.code, []):
        cast_queue.setdefault(cast_entry["role"], []).append(cast_entry)

    # A club leans towards a couple of name flavours, as real squads have recruitment patterns.
    # Names come from their own random stream, so rejecting a name never changes anyone's attributes.
    tilt = {
        k: float(np.exp(name_rng.normal(0, 0.5)))
        for k in ("english", "west_african", "iberian", "balkan", "nordic", "french", "irish_scottish", "east_asian")
    }
    numbers_taken: set[int] = set()
    surnames_taken: set[str] = {entry["surname"] for entry in CAST.get(spec.code, [])}
    players: list[Player] = []
    cast_players: list[tuple[Player, dict]] = []
    for role in SQUAD_ROLES:
        attrs = _attrs_for(role, spec.quality, rng)
        height = int(round(ROLE_ATTRS[role]["height"] + rng.normal(0, 5)))
        foot = "L" if rng.random() < (0.6 if role in ("LB", "LW") else 0.2) else "R"
        queue = cast_queue.get(role)
        entry: dict | None = queue.pop(0) if queue else None
        if entry is not None:
            given, surname, shirt = entry["given"], entry["surname"], entry["shirt"]
            foot, height = entry["foot"], entry["height"]
        else:
            # "Dellow" and "Dellington" in one squad would be confusing in commentary and in
            # the described feed, so stems are checked as well as whole surnames.
            squad_stems = {s[:3].lower() for s in surnames_taken}
            while True:
                given, surname = generate_name(pick_flavour(name_rng, tilt), name_rng)
                if (
                    f"{given} {surname}" not in BLOCKED_NAMES
                    and f"{given} {surname}" not in used_names
                    and surname not in used_surnames
                    and len(surname) >= 4
                    and surname[:3].lower() not in squad_stems
                    and surname[:4].lower() not in cast_stems
                ):
                    break
            shirt = 0
        used_names.add(f"{given} {surname}")
        used_surnames.add(surname)
        surnames_taken.add(surname)
        player = Player(
            id="",
            club=club.id,
            given=given,
            surname=surname,
            shirt=shirt,
            role=role,
            foot=foot,
            height=height,
            attrs=attrs,
            first_choice=entry is not None,
        )
        players.append(player)
        if entry is not None:
            cast_players.append((player, entry))
        if shirt:
            numbers_taken.add(shirt)

    # The named cast are first choice in their roles: each listed attribute ends at least as
    # high as the listed value and above every squad-mate in the same role.
    for player, entry in cast_players:
        mates = [q for q in players if q.role == player.role and q is not player]
        for key, value in entry["attrs"].items():
            best_mate = max((q.attrs[key] for q in mates), default=0.0)
            player.attrs[key] = float(min(max(value, best_mate + 0.02), 0.99 if key != "top_speed" else 10.2))

    # First-choice numbers go to the best player in each role; the rest take 12+.
    by_role: dict[str, list[Player]] = {}
    for p in players:
        by_role.setdefault(p.role, []).append(p)
    for role, group in by_role.items():
        group.sort(key=lambda p: -_role_rating(p, role))
        number = FIRST_CHOICE_NUMBER.get(role)
        if role == "CB":
            candidates = [4, 5]
        else:
            candidates = [number] if number else []
        for p in group:
            if p.shirt:
                continue
            free = [n for n in candidates if n not in numbers_taken]
            if free:
                p.shirt = free[0]
                numbers_taken.add(p.shirt)
    spare = [n for n in range(12, 40) if n not in numbers_taken]
    rng.shuffle(spare)
    for p in players:
        if not p.shirt:
            p.shirt = int(spare.pop())
            numbers_taken.add(p.shirt)
    for p in players:
        p.id = f"{club.id}-{p.shirt:02d}"
    club.squad = players


def _role_rating(p: Player, slot_role: str) -> float:
    """How well a player suits a slot role, on a 0-1 scale."""
    a = p.attrs
    if slot_role == "GK":
        return (a["gk_skill"] + a["handling"]) / 2 if p.role == "GK" else 0.0
    weights = {
        "CB": dict(tackling=0.3, marking=0.3, heading=0.25, passing=0.15),
        "RB": dict(tackling=0.25, marking=0.2, dribbling=0.2, passing=0.2, top_speed=0.15),
        "LB": dict(tackling=0.25, marking=0.2, dribbling=0.2, passing=0.2, top_speed=0.15),
        "DM": dict(tackling=0.3, passing=0.3, marking=0.2, vision=0.2),
        "CM": dict(passing=0.35, vision=0.25, first_touch=0.2, tackling=0.2),
        "AM": dict(passing=0.3, vision=0.3, dribbling=0.2, long_shots=0.2),
        "RW": dict(dribbling=0.35, top_speed=0.25, finishing=0.2, passing=0.2),
        "LW": dict(dribbling=0.35, top_speed=0.25, finishing=0.2, passing=0.2),
        "ST": dict(finishing=0.45, heading=0.2, first_touch=0.2, top_speed=0.15),
    }[slot_role]
    score = 0.0
    for k, w in weights.items():
        v = (a[k] - 7.5) / 2.5 if k == "top_speed" else a[k]
        score += w * v
    fit = ROLE_FIT[slot_role]
    if p.role not in fit:
        return 0.0
    return score * (1.0 - 0.08 * fit.index(p.role))


def _best_for(players: list[Player], slot_role: str) -> Player:
    ratings = [_role_rating(p, slot_role) for p in players]
    return players[int(np.argmax(ratings))]


def pick_lineup(club: Club, unavailable: set[str] | None = None) -> tuple[list[Player], list[Player]]:
    """Choose the starting eleven in formation slot order, and a bench of nine.

    Slots are filled in three passes: first-choice players into a slot of their own
    role, then the best remaining player whose own role matches each slot, then the
    best fit from neighbouring roles for any slot still empty.
    """
    unavailable = unavailable or set()
    slots = FORMATIONS[club.formation]
    available = [p for p in club.squad if p.id not in unavailable]
    filled: list[Player | None] = [None] * len(slots)
    used: set[str] = set()
    for p in (p for p in available if p.first_choice):
        for i, slot in enumerate(slots):
            if filled[i] is None and slot.role == p.role:
                filled[i] = p
                used.add(p.id)
                break
    for i, slot in enumerate(slots):
        if filled[i] is None:
            natural = [p for p in available if p.id not in used and p.role == slot.role]
            if natural:
                best = _best_for(natural, slot.role)
                filled[i] = best
                used.add(best.id)
    for i, slot in enumerate(slots):
        if filled[i] is None:
            best = _best_for([p for p in available if p.id not in used], slot.role)
            filled[i] = best
            used.add(best.id)
    chosen = [p for p in filled if p is not None]
    rest = [p for p in available if p.id not in used]
    bench_gk = [p for p in rest if p.role == "GK"][:1]
    outfield = sorted(
        (p for p in rest if p.role != "GK"),
        key=lambda p: -max(_role_rating(p, r) for r in ("CB", "RB", "DM", "CM", "AM", "RW", "ST")),
    )
    return chosen, bench_gk + outfield[:8]


def build_league(seed: int = 2026) -> League:
    rng = make_rng(seed, "officials")
    used_names: set[str] = {f"{c['given']} {c['surname']}" for entries in CAST.values() for c in entries}
    used_surnames: set[str] = {c["surname"] for entries in CAST.values() for c in entries}
    clubs: list[Club] = []
    for spec in CLUB_SPECS:
        club_rng = make_rng(seed, "club", spec.code)
        style = _style_for(spec, club_rng)
        formation = spec.formation or ARCHETYPE_FORMATION[spec.archetype]
        club = Club(spec=spec, style=style, formation=formation)
        _build_squad(club, club_rng, make_rng(seed, "names", spec.code), used_names, used_surnames)
        clubs.append(club)
    referees: list[Official] = []
    cast_stems = {e["surname"][:4].lower() for entries in CAST.values() for e in entries}
    while len(referees) < N_REFEREES:
        given, surname = generate_name("english", rng)
        if surname in used_surnames or surname[:4].lower() in cast_stems or f"{given} {surname}" in BLOCKED_NAMES:
            continue
        used_surnames.add(surname)
        referees.append(Official(id=f"ref-{len(referees) + 1:02d}", name=f"{given} {surname}"))
    return League(seed=seed, name=LEAGUE_NAME, season=SEASON, clubs=clubs, referees=referees)
