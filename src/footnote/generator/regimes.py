"""Hidden match states ("regimes").

A regime is the latent shape of play at a moment in the match. It is never
written to the feed; it changes how both teams behave, and the events they
produce are the only evidence of it. The answer key records the true regime
timeline so a state model can be scored against it.

Regimes:

- control (team): settled possession; the other side defends without pressing high
- pressure (team): the team is camped in the opponent's half, winning the ball back quickly
- transition (team): the team is breaking at speed after winning the ball
- chaos: neither side controls; the ball changes hands often and play is direct
- balanced: an even, open contest

The process is semi-Markov. A regime is entered with a planned duration; when it
expires the next regime is drawn with weights that depend on team styles and
strengths, the score and the clock. A regain can cut a regime short by starting
a transition for the team that won the ball; when the transition ends, the
regime it interrupted resumes if its time hasn't run out.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np


class Kind(StrEnum):
    CONTROL = "control"
    PRESSURE = "pressure"
    TRANSITION = "transition"
    CHAOS = "chaos"
    BALANCED = "balanced"


TEAM_KINDS = (Kind.CONTROL, Kind.PRESSURE, Kind.TRANSITION)


@dataclass(frozen=True)
class Regime:
    kind: Kind
    team: int | None = None  # 0 home, 1 away; None for chaos and balanced

    @property
    def label(self) -> str:
        return self.kind.value if self.team is None else f"{self.kind.value}:{'home' if self.team == 0 else 'away'}"

    def role_of(self, team: int) -> str:
        """'lead' if the regime belongs to this team, 'other' if to the opponent, 'none' otherwise."""
        if self.team is None:
            return "none"
        return "lead" if self.team == team else "other"


@dataclass(frozen=True)
class Intent:
    """Behaviour parameters for one team at one moment, derived from style and regime."""

    risk: float  # weight on forward progress when choosing a pass
    caution: float  # weight on the cost of losing the ball
    retention: float  # logit shift on pass completion (pressure and passing options)
    tempo: float  # multiplier on time on the ball (lower is quicker)
    press: float  # 0-1 pressing intensity without the ball
    territory: float  # metres added to the team's block position
    long_ball: float  # preference for lofted forward passes and clearances
    cross: float  # preference for crossing from wide areas
    shoot: float  # multiplier on shot appetite
    carry: float  # multiplier on carrying the ball forward
    urgency: float  # 0-1 how hard off-ball players run
    foul: float  # logit shift on foul probability in duels


# Regime effects by the team's role in it and whether it has the ball.
# Columns: risk, caution, retention, tempo, press, territory, long_ball, cross, shoot, carry, urgency, foul
_EFFECTS: dict[tuple[Kind, str, bool], tuple[float, ...]] = {
    (Kind.CONTROL, "lead", True): (0.80, 1.20, 0.30, 1.10, 1.0, 8.0, 0.55, 0.85, 0.90, 0.90, 0.55, 0.0),
    (Kind.CONTROL, "lead", False): (1.0, 1.0, 0.0, 1.0, 1.35, 8.0, 1.0, 1.0, 1.0, 1.0, 0.85, 0.0),
    (Kind.CONTROL, "other", True): (1.05, 1.00, 0.00, 0.90, 1.0, -9.0, 1.15, 1.0, 1.0, 1.0, 0.65, 0.0),
    (Kind.CONTROL, "other", False): (1.0, 1.0, 0.0, 1.0, 0.55, -9.0, 1.0, 1.0, 1.0, 1.0, 0.55, -0.1),
    (Kind.PRESSURE, "lead", True): (1.10, 0.85, 0.10, 0.95, 1.0, 16.0, 0.80, 1.70, 1.45, 1.0, 0.75, 0.0),
    (Kind.PRESSURE, "lead", False): (1.0, 1.0, 0.0, 1.0, 1.60, 16.0, 1.0, 1.0, 1.0, 1.0, 0.95, 0.1),
    (Kind.PRESSURE, "other", True): (1.30, 0.70, -0.25, 0.80, 1.0, -18.0, 1.80, 1.0, 1.0, 0.9, 0.70, 0.0),
    (Kind.PRESSURE, "other", False): (1.0, 1.0, 0.0, 1.0, 0.60, -18.0, 1.0, 1.0, 1.0, 1.0, 0.60, 0.1),
    (Kind.TRANSITION, "lead", True): (1.90, 0.60, -0.05, 0.55, 1.0, 0.0, 1.20, 1.10, 1.35, 1.70, 1.00, 0.0),
    (Kind.TRANSITION, "lead", False): (1.0, 1.0, 0.0, 1.0, 1.20, 0.0, 1.0, 1.0, 1.0, 1.0, 0.95, 0.0),
    (Kind.TRANSITION, "other", True): (1.20, 0.90, -0.20, 0.85, 1.0, -4.0, 1.40, 1.0, 1.0, 1.0, 0.80, 0.0),
    (Kind.TRANSITION, "other", False): (1.0, 1.0, 0.0, 1.0, 0.85, -4.0, 1.0, 1.0, 1.0, 1.0, 1.00, 0.35),
    (Kind.CHAOS, "none", True): (1.40, 0.75, -0.30, 0.75, 1.0, 0.0, 1.80, 1.20, 1.15, 1.10, 0.80, 0.30),
    (Kind.CHAOS, "none", False): (1.0, 1.0, 0.0, 1.0, 1.25, 0.0, 1.0, 1.0, 1.0, 1.0, 0.85, 0.30),
    (Kind.BALANCED, "none", True): (1.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 1.0, 1.0, 1.0, 0.65, 0.0),
    (Kind.BALANCED, "none", False): (1.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 1.0, 1.0, 1.0, 0.70, 0.0),
}


def intent(regime: Regime, team: int, style: dict[str, float], in_possession: bool) -> Intent:
    """Combine a team's style with the current regime into behaviour parameters."""
    e = _EFFECTS[(regime.kind, regime.role_of(team), in_possession)]
    risk, caution, retention, tempo, press, territory, long_ball, cross, shoot, carry, urgency, foul = e
    return Intent(
        risk=(0.85 + 0.3 * style["directness"]) * risk,
        caution=(1.1 + 0.3 * style["possession"]) * caution,
        retention=retention,
        tempo=(1.15 - 0.3 * style["tempo"]) * tempo,
        press=float(np.clip(style["press"] * press, 0.0, 1.0)),
        territory=territory + 10.0 * (style["line"] - 0.5),
        long_ball=(0.25 + 0.6 * style["aerial"] * style["directness"]) * long_ball,
        cross=(0.35 + 0.9 * style["width"]) * cross,
        shoot=shoot,
        carry=(0.8 + 0.4 * style["directness"]) * carry,
        urgency=urgency,
        foul=foul + 1.2 * (style["aggression"] - 0.5),
    )


# Mean planned durations in seconds of match time (gamma-distributed, shape 2.5).
_MEAN_DURATION = {Kind.CONTROL: 210.0, Kind.PRESSURE: 140.0, Kind.CHAOS: 150.0, Kind.BALANCED: 200.0}
_SHAPE = 2.5
TRANSITION_MAX = 40.0


@dataclass
class TeamProfile:
    """What the regime process needs to know about a team."""

    style: dict[str, float]
    quality: float


@dataclass
class Segment:
    regime: Regime
    period: int
    start: float
    end: float | None = None


@dataclass
class RegimeProcess:
    teams: tuple[TeamProfile, TeamProfile]
    home_edge: float = 0.07
    current: Regime = field(default_factory=lambda: Regime(Kind.BALANCED))
    planned_end: float = 0.0
    suspended: tuple[Regime, float] | None = None
    transition_start: float = 0.0
    log: list[Segment] = field(default_factory=list)

    # ----- entering and leaving regimes -------------------------------------------------

    def _enter(self, regime: Regime, period: int, t: float, planned_end: float) -> None:
        if self.log and self.log[-1].end is None:
            self.log[-1].end = t
        self.current = regime
        self.planned_end = planned_end
        self.log.append(Segment(regime=regime, period=period, start=t))

    def start_period(self, period: int, t: float, context: dict, rng: np.random.Generator) -> None:
        self.suspended = None
        regime = self._draw_next(context, rng, exclude=None)
        self._enter(regime, period, t, t + self._draw_duration(regime, rng))

    def end_period(self, t: float) -> None:
        if self.log and self.log[-1].end is None:
            self.log[-1].end = t

    def _draw_duration(self, regime: Regime, rng: np.random.Generator) -> float:
        mean = _MEAN_DURATION[regime.kind]
        if regime.team is not None:
            style = self.teams[regime.team].style
            if regime.kind is Kind.CONTROL:
                mean *= 0.7 + 0.5 * style["possession"]
            elif regime.kind is Kind.PRESSURE:
                mean *= 0.7 + 0.5 * style["press"]
        return float(rng.gamma(_SHAPE, mean / _SHAPE))

    def _weights(self, context: dict) -> tuple[list[Regime], np.ndarray]:
        h, a = self.teams
        diff = h.quality - a.quality + self.home_edge
        minute = context.get("minute", 0.0)
        goal_diff = context.get("goal_diff", 0)  # home minus away
        late = max(0.0, (minute - 60.0) / 30.0)
        options: list[Regime] = []
        logits: list[float] = []
        for team, sign in ((0, 1.0), (1, -1.0)):
            s = self.teams[team].style
            trailing = 1.0 if sign * goal_diff < 0 else 0.0
            leading = 1.0 if sign * goal_diff > 0 else 0.0
            options.append(Regime(Kind.CONTROL, team))
            logits.append(
                0.5 + 1.0 * (s["possession"] - 0.5) + 1.6 * sign * diff + 0.5 * trailing * late - 0.4 * leading * late
            )
            options.append(Regime(Kind.PRESSURE, team))
            logits.append(
                -0.3
                + 1.2 * (s["press"] - 0.5)
                + 1.4 * sign * diff
                + 1.2 * trailing * late
                + 0.3 * trailing
                - 0.5 * leading * late
            )
        hs, as_ = h.style, a.style
        close = 1.0 if abs(goal_diff) <= 1 else 0.0
        options.append(Regime(Kind.CHAOS))
        logits.append(
            0.5
            + 1.4 * (hs["directness"] + as_["directness"] - 1.0)
            + 0.8 * (hs["aggression"] + as_["aggression"] - 1.0)
            + 0.9 * late * close
        )
        options.append(Regime(Kind.BALANCED))
        logits.append(1.5 - 1.0 * abs(diff))
        return options, np.array(logits)

    def _draw_next(self, context: dict, rng: np.random.Generator, exclude: Regime | None) -> Regime:
        options, logits = self._weights(context)
        if exclude is not None:
            logits = logits - np.array([1.0 if o == exclude else 0.0 for o in options])
        p = np.exp(logits - logits.max())
        p /= p.sum()
        return options[int(rng.choice(len(options), p=p))]

    # ----- updates driven by the simulation ----------------------------------------------

    def tick(self, period: int, t: float, context: dict, rng: np.random.Generator) -> None:
        """Called before each action. Ends regimes whose time has run out."""
        if self.current.kind is Kind.TRANSITION:
            if t - self.transition_start > TRANSITION_MAX:
                self.end_transition(period, t, context, rng)
            return
        if t >= self.planned_end:
            nxt = self._draw_next(context, rng, exclude=self.current)
            self._enter(nxt, period, t, t + self._draw_duration(nxt, rng))

    def on_regain(
        self,
        period: int,
        t: float,
        team: int,
        regain_u: float,
        opponents_ahead: int,
        context: dict,
        rng: np.random.Generator,
    ) -> bool:
        """A team won the ball. Returns True if it starts a transition.

        regain_u is where the ball was won, in the winning team's frame; opponents_ahead is
        how many outfield opponents were goal-side of the ball at that moment.
        """
        if self.current.kind is Kind.TRANSITION:
            if self.current.team != team:
                # The breaking side lost the ball; its transition is over.
                self.end_transition(period, t, context, rng)
            return False
        s = self.teams[team].style
        interrupted = self.current.kind in (Kind.CONTROL, Kind.PRESSURE) and self.current.team != team
        logit = (
            -3.0
            + 3.0 * (s["counter"] - 0.5)
            + 0.06 * (regain_u - 40.0)
            + 0.45 * (6 - opponents_ahead)
            + (0.9 if interrupted else 0.0)
            - (0.6 if self.current.kind is Kind.CHAOS else 0.0)
        )
        if rng.random() >= 1.0 / (1.0 + np.exp(-logit)):
            return False
        self.suspended = (self.current, self.planned_end)
        self.transition_start = t
        self._enter(Regime(Kind.TRANSITION, team), period, t, t + TRANSITION_MAX)
        return True

    def end_transition(self, period: int, t: float, context: dict, rng: np.random.Generator) -> None:
        if self.current.kind is not Kind.TRANSITION:
            return
        if self.suspended is not None and self.suspended[1] > t + 20.0:
            regime, planned_end = self.suspended
        else:
            regime = self._draw_next(context, rng, exclude=None)
            planned_end = t + self._draw_duration(regime, rng)
        self.suspended = None
        self._enter(regime, period, t, planned_end)

    def on_goal(self, period: int, t: float, context: dict, rng: np.random.Generator) -> None:
        """After a goal the old pattern rarely survives the restart."""
        self.suspended = None
        nxt = self._draw_next(context, rng, exclude=None)
        self._enter(nxt, period, t, t + self._draw_duration(nxt, rng))

    def timeline(self) -> list[dict]:
        return [
            dict(
                regime=s.regime.kind.value,
                team=s.regime.team,
                label=s.regime.label,
                period=s.period,
                start=round(s.start, 2),
                end=round(s.end, 2) if s.end is not None else None,
            )
            for s in self.log
        ]
