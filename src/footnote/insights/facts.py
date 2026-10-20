"""Facts: what a card may state, each figure and name computed by code.

A card never carries a figure that code didn't compute (docs/audience.md, P2). Wording, whether a
template's or an agent's, puts a placeholder where each figure goes, `{teams.SAL.possession}`, and
code fills it in from the facts (draft.py). A fact has its value, the text a card shows for it, a
line saying what it is for whoever writes the card, and the events it rests on when there are
particular ones.

Keys are dotted paths: `moment.*` for the moment's own figures, `teams.<CODE>.*` and `score.*` for
the match, `state.*` for the match-state model, `player.<id>.*` and `event.<id>.*` for players and
events.
"""

from __future__ import annotations

from dataclasses import dataclass

NBSP = chr(0xA0)  # between a figure and its unit, so the two never wrap apart
EN_DASH = chr(0x2013)

Value = str | int | float | bool | None


@dataclass(frozen=True)
class Fact:
    value: Value
    display: str
    about: str
    events: tuple[str, ...] = ()

    def to_json(self) -> dict:
        out: dict = {"value": self.value, "display": self.display, "about": self.about}
        if self.events:
            out["events"] = list(self.events)
        return out

    @classmethod
    def from_json(cls, data: dict) -> Fact:
        return cls(data["value"], data["display"], data["about"], tuple(data.get("events", ())))


Facts = dict[str, Fact]


def facts_to_json(facts: Facts) -> dict[str, dict]:
    return {key: fact.to_json() for key, fact in facts.items()}


def facts_from_json(data: dict[str, dict]) -> Facts:
    return {key: Fact.from_json(value) for key, value in data.items()}


def text(value: str, about: str, events: tuple[str, ...] = ()) -> Fact:
    """A name or a phrase, shown as it is."""
    return Fact(value, value, about, events)


def count(value: int, about: str, events: tuple[str, ...] = ()) -> Fact:
    return Fact(value, str(value), about, events)


def share(value: float, about: str, events: tuple[str, ...] = ()) -> Fact:
    """A share between 0 and 1, shown as a whole percentage."""
    return Fact(round(value, 3), f"{round(value * 100)}%", about, events)


def rating(value: float, about: str, events: tuple[str, ...] = ()) -> Fact:
    """A model rating between 0 and 1, shown to two decimals, as the stats panel shows difficulty."""
    return Fact(round(value, 2), f"{value:.2f}", about, events)


def speed(kmh: float, about: str, events: tuple[str, ...] = ()) -> Fact:
    return Fact(round(kmh, 1), f"{kmh:.1f}{NBSP}km/h", about, events)


def metres(value: float, about: str, events: tuple[str, ...] = ()) -> Fact:
    return Fact(round(value, 1), f"{round(value)}{NBSP}m", about, events)


def kilometres(value: float, about: str, events: tuple[str, ...] = ()) -> Fact:
    return Fact(round(value, 2), f"{value:.1f}{NBSP}km", about, events)


def minute_label(minute: int, added: int | None) -> str:
    """As a broadcast shows it: 23' in normal time, 45+2' in added time."""
    return f"{minute}'" if added is None else f"{minute}+{added}'"


def minute(minute: int, added: int | None, about: str, events: tuple[str, ...] = ()) -> Fact:
    return Fact(minute, minute_label(minute, added), about, events)


def duration(seconds: float, about: str, events: tuple[str, ...] = ()) -> Fact:
    """A spell's length as a viewer would say it: seconds under two minutes, whole minutes after."""
    s = round(seconds)
    shown = f"{s} seconds" if s < 120 else f"{s // 60} minutes"
    return Fact(s, shown, about, events)


def score_line(home_name: str, home: int, away: int, away_name: str) -> str:
    return f"{home_name} {home}{EN_DASH}{away} {away_name}"
