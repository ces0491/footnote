"""Formation templates.

Each slot sits in "shape space": row runs from 0 (the defensive line) to 1 (the
front line) and col from -0.5 (the team's right touchline side) to +0.5 (its
left), as fractions of the team's current length and width. The shape model in
movement.py scales these to metres around the team's block.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Slot:
    name: str
    role: str
    row: float
    col: float

    @property
    def line(self) -> str:
        if self.role == "GK":
            return "gk"
        if self.row < 0.2:
            return "def"
        if self.row < 0.8:
            return "mid"
        return "att"


GK = Slot("GK", "GK", -1.0, 0.0)

FORMATIONS: dict[str, tuple[Slot, ...]] = {
    "4-3-3": (
        GK,
        Slot("RB", "RB", 0.0, -0.5),
        Slot("RCB", "CB", 0.0, -0.17),
        Slot("LCB", "CB", 0.0, 0.17),
        Slot("LB", "LB", 0.0, 0.5),
        Slot("DM", "DM", 0.3, 0.0),
        Slot("RCM", "CM", 0.52, -0.24),
        Slot("LCM", "CM", 0.52, 0.24),
        Slot("RW", "RW", 0.95, -0.42),
        Slot("ST", "ST", 1.0, 0.0),
        Slot("LW", "LW", 0.95, 0.42),
    ),
    "4-2-3-1": (
        GK,
        Slot("RB", "RB", 0.0, -0.5),
        Slot("RCB", "CB", 0.0, -0.17),
        Slot("LCB", "CB", 0.0, 0.17),
        Slot("LB", "LB", 0.0, 0.5),
        Slot("RDM", "DM", 0.32, -0.14),
        Slot("LDM", "CM", 0.32, 0.14),
        Slot("RW", "RW", 0.72, -0.42),
        Slot("AM", "AM", 0.72, 0.0),
        Slot("LW", "LW", 0.72, 0.42),
        Slot("ST", "ST", 1.0, 0.0),
    ),
    "4-4-2": (
        GK,
        Slot("RB", "RB", 0.0, -0.5),
        Slot("RCB", "CB", 0.0, -0.17),
        Slot("LCB", "CB", 0.0, 0.17),
        Slot("LB", "LB", 0.0, 0.5),
        Slot("RM", "RW", 0.5, -0.45),
        Slot("RCM", "CM", 0.45, -0.14),
        Slot("LCM", "DM", 0.45, 0.14),
        Slot("LM", "LW", 0.5, 0.45),
        Slot("RS", "ST", 1.0, -0.11),
        Slot("LS", "ST", 1.0, 0.11),
    ),
    "3-4-3": (
        GK,
        Slot("RCB", "CB", 0.0, -0.3),
        Slot("CB", "CB", 0.0, 0.0),
        Slot("LCB", "CB", 0.0, 0.3),
        Slot("RWB", "RB", 0.42, -0.5),
        Slot("RCM", "CM", 0.42, -0.14),
        Slot("LCM", "DM", 0.42, 0.14),
        Slot("LWB", "LB", 0.42, 0.5),
        Slot("RW", "RW", 0.9, -0.3),
        Slot("ST", "ST", 1.0, 0.0),
        Slot("LW", "LW", 0.9, 0.3),
    ),
}

# Which squad roles can fill a slot role, best fit first.
ROLE_FIT: dict[str, tuple[str, ...]] = {
    "GK": ("GK",),
    "CB": ("CB", "DM"),
    "RB": ("RB", "LB", "CB", "RW"),
    "LB": ("LB", "RB", "CB", "LW"),
    "DM": ("DM", "CM", "CB"),
    "CM": ("CM", "DM", "AM"),
    "AM": ("AM", "CM", "RW", "LW"),
    "RW": ("RW", "LW", "AM", "ST"),
    "LW": ("LW", "RW", "AM", "ST"),
    "ST": ("ST", "AM", "RW", "LW"),
}
