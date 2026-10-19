"""How the simulated officials judge what happened.

The simulation knows the truth: every player's position at the moment of a
pass, and whether an arm was in an unnatural position. Officials see it with
error. The assistant referee's flag depends on the offside margin and, for close
calls in promising attacks, waits (the delayed-flag protocol) so VAR can decide
if a goal follows. VAR reviews goals (offside and fouls in the build-up), every
penalty, and handball claims, and intervenes on clear errors.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from footnote.generator.models import sigmoid


@dataclass(frozen=True)
class FlagDecision:
    flag: bool  # flag raised at once: play stops for offside
    delayed: bool  # close call in a promising attack: flag held until the move ends


def assistant_offside_call(margin: float, promising: bool, rng: np.random.Generator) -> FlagDecision:
    """The assistant referee's call on a receiver `margin` metres beyond the offside line.

    Positive margins are offside. Clear offsides are flagged; close ones in promising
    attacks are held for VAR; a player onside by a whisker is occasionally flagged.
    """
    p_sees_offside = float(sigmoid((margin - 0.15) / 0.20))
    sees_offside = rng.random() < p_sees_offside
    if not sees_offside:
        return FlagDecision(flag=False, delayed=False)
    if promising and margin < 0.9:
        return FlagDecision(flag=False, delayed=True)
    return FlagDecision(flag=True, delayed=False)


VAR_OFFSIDE_PRECISION = 0.03  # metres; line-drawing error at the VAR hub

# Share of goals with a foul by the attacking side in the build-up that the referee missed.
# VAR reviews these and disallows most. Tuned so total VAR overturns land near the published
# season count (see docs/calibration.md).
APP_FOUL_RATE = 0.045

# Share of won tackles in the defender's own box that were in fact fouls the referee missed and
# VAR picks up. Tuned with APP_FOUL_RATE against the published overturn count.
MISSED_BOX_FOUL_RATE = 0.035


def var_offside_check(margin: float, rng: np.random.Generator) -> bool:
    """VAR's verdict on an offside margin: True means offside."""
    return margin + rng.normal(0.0, VAR_OFFSIDE_PRECISION) > 0.0


def arm_contact(rng: np.random.Generator, close_range: bool) -> bool:
    """Did a ball that struck a defender hit their arm?"""
    return rng.random() < (0.07 if close_range else 0.11)


def arm_unnatural(rng: np.random.Generator) -> bool:
    """Was the arm in an unnatural position (making the body bigger)? The answer key keeps this."""
    return rng.random() < 0.38


def referee_awards_handball(unnatural: bool, rng: np.random.Generator) -> bool:
    return rng.random() < (0.55 if unnatural else 0.05)


def var_corrects(on_field: bool, truth: bool, rng: np.random.Generator) -> bool:
    """Does VAR overturn an on-field call that disagrees with the truth? Only clear and obvious errors,
    so not every wrong call."""
    if on_field == truth:
        return False
    return rng.random() < 0.8


def foul_card(
    severity: float, tactical: bool, denies_goal_chance: bool, rng: np.random.Generator, booked: bool = False
) -> str | None:
    """Card for a foul: None, 'yellow' or 'red'. severity is 0-1; booked means already on a yellow."""
    if denies_goal_chance and rng.random() < 0.3:
        return "red"
    if rng.random() < 0.0015 + 0.012 * severity**3:
        return "red"
    p_yellow = 0.13 + 0.30 * severity**2 + (0.45 if tactical else 0.0)
    if booked:
        # Referees think twice before a second caution.
        p_yellow *= 0.3
    if rng.random() < min(p_yellow, 0.9):
        return "yellow"
    return None


def added_minutes(time_lost: float, rng: np.random.Generator) -> int:
    """The fourth official's board: whole minutes for time lost in the half, at least one."""
    # Time lost is counted for goals, substitutions, injuries, VAR, penalties and red cards; the
    # extra allowance covers time-wasting and other delays the simulation doesn't track.
    minutes = time_lost / 60.0 + rng.normal(1.6, 0.6)
    return int(np.clip(math.floor(max(minutes, 1.0)), 1, 15))
