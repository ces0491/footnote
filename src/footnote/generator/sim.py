"""The match simulation.

Turn by turn: the player on the ball takes time to control it while the nearest
opponents close in, may be challenged, then chooses an action (decide.py) whose
outcome is drawn from the true probability models (models.py). Every player
moves towards a shape target between actions (movement.py). Officials judge
offside from positions at the moment of the pass, and handball and fouls with
error (officials.py). The hidden regime (regimes.py) shapes both teams'
behaviour throughout.

The simulation writes three logs: raw events with the truth attached (feed.py
splits them into the feed and the answer key), keyframes of every player and
the ball (tracking.py interpolates them), and the regime timeline.

Positions in the state are absolute; decisions are taken in the acting team's
frame (see pitch.py).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import TypedDict

import numpy as np

from footnote.generator import decide, models, officials, setpieces
from footnote.generator.formations import FORMATIONS, ROLE_FIT, Slot
from footnote.generator.league import Club, Official, Player, pick_lineup
from footnote.generator.movement import move, offside_line, shape_targets
from footnote.generator.pitch import (
    HALF_WIDTH,
    LENGTH,
    PENALTY_SPOT,
    WIDTH,
    dist_to_goal,
    exit_point,
    in_attacking_box,
    in_own_box,
    to_frame,
)
from footnote.generator.regimes import Intent, Kind, RegimeProcess, TeamProfile, intent
from footnote.generator.rng import make_rng

PERIOD_SECONDS = 45 * 60
TEAM_SIZE = 11
MAX_SUBS = 5
# Mean of forwards' run-timing error against the offside line, in metres (negative is onside).
RUN_OFFSET_MEAN = -3.0
# Home advantage, in the same units as club quality.
HOME_EDGE = 0.18
# Running effort, tuned against published distance, high-intensity and sprint figures
# (docs/calibration.md). EFFORT scales the regime's urgency; URGENT is the share of top speed for
# a player chasing something (pressing, a loose ball); SPECIAL for one with a set target (a
# receiver). ARRIVE is how many seconds a player takes to close on a target; JITTER_* shape the
# slow personal drift that keeps players moving between actions.
EFFORT = 0.88
URGENT = 0.9
SPECIAL = 0.85
ARRIVE = 2.0
ARRIVE_CHASING = 1.0
JITTER_SD = 2.6
JITTER_TIME = 10.0
# Stoppages are played out in spells of STOPPAGE_STEP seconds, with players wandering MILL_SD metres
# around their positions.
STOPPAGE_STEP = 5.0
MILL_SD = 2.0


class XY(TypedDict):
    x: float
    y: float


class EndXY(TypedDict):
    end_x: float
    end_y: float


@dataclass
class Restart:
    kind: str  # kick_off, throw_in, goal_kick, corner, free_kick, penalty, drop_ball
    team: int
    spot: np.ndarray  # absolute
    dead_time: float


@dataclass
class OffsideOffence:
    """A receiver in an offside position who was not flagged at once."""

    pass_event: int
    player: int
    margin: float
    spot: np.ndarray  # absolute position when the ball was played
    delayed: bool  # the assistant saw it and is holding the flag


@dataclass
class Keyframe:
    period: int
    t: float
    pos: np.ndarray
    ball: np.ndarray  # x, y, z at this instant
    active: np.ndarray
    occupancy: int
    ball_path: tuple  # how the ball moved since the previous keyframe


@dataclass
class State:
    rng: np.random.Generator
    occupants: list[str]
    attrs: list[dict[str, float]]
    roles: list[str]
    active: np.ndarray
    pos: np.ndarray
    vel: np.ndarray
    jitter: np.ndarray
    run_offsets: np.ndarray
    entered_at: np.ndarray  # match seconds when each occupant came on
    regimes: RegimeProcess
    bench: list[list[str]]
    sub_plan: list[list[float]]  # each side's substitution windows, in match minutes
    sub_budget: list[int]  # how many substitutions each side means to make
    period: int = 1
    started_period: int = 0
    t: float = 0.0
    period_end: float | None = None
    direction: list[int] = field(default_factory=lambda: [1, -1])
    score: list[int] = field(default_factory=lambda: [0, 0])
    ball: np.ndarray = field(default_factory=lambda: np.array([LENGTH / 2, HALF_WIDTH, 0.0]))
    carrier: int = -1
    poss_team: int = 0
    possession_seq: int = 0
    restart: Restart | None = None
    time_lost: float = 0.0
    offences: list[OffsideOffence] = field(default_factory=list)
    last_pass: tuple[int, int, int] | None = None  # (event index, passer, receiver)
    last_touch_team: int = 0
    yellow: dict[str, int] = field(default_factory=dict)
    subs_made: list[int] = field(default_factory=lambda: [0, 0])
    windows_used: list[int] = field(default_factory=lambda: [0, 0])
    transition_best: tuple[float, float] = (0.0, 0.0)  # (ball u, time) for stall detection
    last_pressure: tuple[int, float] = (-1, -10.0)
    # How the current possession began: a restart kind, "regular_play" or "counter".
    play_pattern: str = "kick_off"
    restart_at: float = 0.0  # clock time the last restart was taken
    final_third_since: float | None = None  # when the team in possession settled in the final third
    occupancy_version: int = 0
    reseed_index: int = 0
    steps: int = 0  # step() calls so far; reseeds are keyed to it
    kickoff_team: int = 0
    finished: bool = False


@dataclass
class Snapshot:
    state: State
    n_events: int
    n_keyframes: int
    n_occupancy: int


@dataclass
class TeamSheet:
    club: Club
    formation: str
    slots: tuple[Slot, ...]
    starters: list[Player]
    bench: list[Player]


class MatchSim:
    def __init__(
        self,
        home: Club,
        away: Club,
        match_id: str,
        seed: int,
        referee: Official,
        players: dict[str, Player],
        reseeds: list[tuple[int, int]] | None = None,
        unavailable: set[str] | None = None,
        protected: set[str] | None = None,
    ) -> None:
        """reseeds: (step, seed) pairs; at the start of that step the random stream is replaced by
        one derived from the seed. A search for a scripted story records these (see showcase.py).
        protected: players who are never substituted."""
        self.match_id = match_id
        self.seed = seed
        self.clubs = (home, away)
        self.referee = referee
        self.players = players
        self.styles = (home.style, away.style)
        # Ordered by step and otherwise as given: if two share a step, the later one is the one that holds,
        # as it did when the search applied them.
        self.reseeds = sorted(reseeds or [], key=lambda r: r[0])
        self.protected = set(protected or ())
        self.sheets: list[TeamSheet] = []
        for club in (home, away):
            starters, bench = pick_lineup(club, unavailable)
            self.sheets.append(TeamSheet(club, club.formation, FORMATIONS[club.formation], starters, bench))
        self.slots: list[Slot] = list(self.sheets[0].slots) + list(self.sheets[1].slots)
        self.team_of = np.array([0] * TEAM_SIZE + [1] * TEAM_SIZE)
        self.events: list[dict] = []
        self.keyframes: list[Keyframe] = []
        rng = make_rng(seed, "match", match_id)
        occupants = [p.id for p in self.sheets[0].starters] + [p.id for p in self.sheets[1].starters]
        regimes = RegimeProcess(teams=(TeamProfile(home.style, home.quality), TeamProfile(away.style, away.quality)))
        sub_plans = [self._plan_subs(rng), self._plan_subs(rng)]
        self.s = State(
            rng=rng,
            occupants=occupants,
            attrs=[self._attrs_of(pid) for pid in occupants],
            roles=[slot.role for slot in self.slots],
            active=np.ones(2 * TEAM_SIZE, dtype=bool),
            pos=np.zeros((2 * TEAM_SIZE, 2)),
            vel=np.zeros((2 * TEAM_SIZE, 2)),
            jitter=np.zeros((2 * TEAM_SIZE, 2)),
            run_offsets=np.full(2 * TEAM_SIZE, RUN_OFFSET_MEAN),
            entered_at=np.zeros(2 * TEAM_SIZE),
            regimes=regimes,
            bench=[[p.id for p in self.sheets[0].bench], [p.id for p in self.sheets[1].bench]],
            sub_plan=[windows for windows, _ in sub_plans],
            sub_budget=[budget for _, budget in sub_plans],
        )
        self.occupancy: list[tuple[str, ...]] = [tuple(occupants)]

    # ------------------------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------------------------

    def _attrs_of(self, pid: str) -> dict[str, float]:
        p = self.players[pid]
        a = dict(p.attrs)
        a["height"] = float(p.height)
        return a

    @staticmethod
    def _plan_subs(rng: np.random.Generator) -> tuple[list[float], int]:
        """A side's substitution plan: up to three windows (match minutes) and how many changes to make.

        Sides make three to five changes, and no more than three when they use a single window.
        """
        n_windows = int(rng.choice([1, 2, 3], p=[0.15, 0.45, 0.40]))
        windows = sorted(float(m) for m in rng.uniform([56, 66, 77][:n_windows], [66, 76, 86][:n_windows]))
        budget = int(rng.choice([3, 4, 5], p=[0.2, 0.3, 0.5]))
        return windows, min(budget, 2 * n_windows + 1)

    # ------------------------------------------------------------------------------------
    # Driving API
    # ------------------------------------------------------------------------------------

    def run(self) -> None:
        while not self.s.finished:
            self.step()

    def snapshot(self) -> Snapshot:
        return Snapshot(copy.deepcopy(self.s), len(self.events), len(self.keyframes), len(self.occupancy))

    def restore(self, snap: Snapshot) -> None:
        self.s = copy.deepcopy(snap.state)
        del self.events[snap.n_events :]
        del self.keyframes[snap.n_keyframes :]
        del self.occupancy[snap.n_occupancy :]

    def reseed(self, seed: int) -> None:
        self.s.rng = make_rng(self.seed, "reseed", seed)

    def step(self) -> None:
        s = self.s
        if s.finished:
            return
        s.steps += 1
        self._apply_due_reseed()
        if s.started_period < s.period:
            self._start_period()
            return
        if s.period_end is None and s.t >= PERIOD_SECONDS:
            minutes = officials.added_minutes(s.time_lost, s.rng)
            self._emit("added_time", minutes=minutes)
            s.period_end = PERIOD_SECONDS + 60.0 * minutes + float(s.rng.uniform(5.0, 40.0))
        if s.period_end is not None and s.t >= s.period_end and self._can_end_period():
            self._end_period()
            return
        if s.restart is not None:
            self._take_restart()
        else:
            self._turn()

    # ------------------------------------------------------------------------------------
    # Periods and the clock
    # ------------------------------------------------------------------------------------

    def _start_period(self) -> None:
        s = self.s
        s.started_period = s.period
        if s.period == 1:
            s.kickoff_team = int(s.rng.integers(2))
            s.direction = [1, -1]
            kick = s.kickoff_team
        else:
            s.direction = [-1, 1]
            kick = 1 - s.kickoff_team
        s.time_lost = 0.0
        s.period_end = None
        s.poss_team = kick
        for team in (0, 1):
            idx = self._team_idx(team)
            targets = setpieces.kickoff_targets(self.sheets[team].slots, s.active[idx], kicking=team == kick)
            s.pos[idx] = to_frame(targets, s.direction[team])
            s.vel[idx] = 0.0
        s.pos[~s.active] = np.array([LENGTH / 2, -1.0])
        s.ball = np.array([LENGTH / 2, HALF_WIDTH, 0.0])
        self._keyframe(("dead", s.ball[:2].copy()))
        self._emit("period_start")
        s.regimes.start_period(s.period, 0.0, self._context(), s.rng)
        s.restart = Restart("kick_off", kick, np.array([LENGTH / 2, HALF_WIDTH]), 0.0)

    def _can_end_period(self) -> bool:
        s = self.s
        if s.restart is not None or s.carrier < 0:
            return True
        team = int(self.team_of[s.carrier])
        u = float(to_frame(s.pos[s.carrier], s.direction[team])[0])
        # A referee lets a promising attack finish, within reason.
        return u < 70.0 or s.t > (s.period_end or 0.0) + 25.0

    def _end_period(self) -> None:
        s = self.s
        self._raise_delayed_flag()
        self._emit("period_end", score=list(s.score))
        s.regimes.end_period(s.t)
        s.restart = None
        s.carrier = -1
        if s.period == 1:
            s.period = 2
            s.t = 0.0
            # Half-time substitutions happen in the break, which isn't simulated.
            for team in (0, 1):
                if s.rng.random() < 0.22:
                    self._make_subs(team, at_half_time=True)
        else:
            self._emit("match_end", score=list(s.score))
            s.finished = True

    def _apply_due_reseed(self) -> None:
        s = self.s
        while s.reseed_index < len(self.reseeds) and self.reseeds[s.reseed_index][0] <= s.steps:
            step, seed = self.reseeds[s.reseed_index]
            if step == s.steps:
                self.reseed(seed)
            s.reseed_index += 1

    def _context(self) -> dict:
        s = self.s
        return dict(minute=s.t / 60.0 + (45.0 if s.period == 2 else 0.0), goal_diff=s.score[0] - s.score[1])

    def match_seconds(self) -> float:
        return self.s.t + (PERIOD_SECONDS if self.s.period == 2 else 0.0)

    # ------------------------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------------------------

    def _pid(self, i: int) -> str:
        return self.s.occupants[i]

    def _emit(self, kind: str, team: int | None = None, player: int | None = None, **fields: object) -> int:
        s = self.s
        ev: dict = dict(type=kind, period=s.period, t=round(s.t, 2), possession=s.possession_seq)
        if team is not None:
            ev["team"] = int(team)
        if player is not None:
            ev["player"] = self._pid(player)
        for k, v in fields.items():
            if isinstance(v, np.floating):
                v = float(v)
            elif isinstance(v, np.integer | np.bool_):
                v = v.item()
            ev[k] = v
        self.events.append(ev)
        return len(self.events) - 1

    @staticmethod
    def _xy(p: np.ndarray) -> XY:
        return XY(x=round(float(p[0]), 2), y=round(float(p[1]), 2))

    @staticmethod
    def _end_xy(p: np.ndarray) -> EndXY:
        return EndXY(
            end_x=round(float(np.clip(p[0], -2, LENGTH + 2)), 2), end_y=round(float(np.clip(p[1], -2, WIDTH + 2)), 2)
        )

    def _freeze_frame(self) -> dict:
        s = self.s
        players = [
            [s.occupants[i], int(self.team_of[i]), round(float(s.pos[i, 0]), 2), round(float(s.pos[i, 1]), 2)]
            for i in range(2 * TEAM_SIZE)
            if s.active[i]
        ]
        return dict(players=players, ball=[round(float(v), 2) for v in s.ball])

    def _keyframe(self, ball_path: tuple) -> None:
        s = self.s
        self.keyframes.append(
            Keyframe(
                s.period, round(s.t, 3), s.pos.copy(), s.ball.copy(), s.active.copy(), s.occupancy_version, ball_path
            )
        )

    # ------------------------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------------------------

    def _team_idx(self, team: int) -> np.ndarray:
        return np.arange(team * TEAM_SIZE, (team + 1) * TEAM_SIZE)

    def _active_idx(self, team: int) -> np.ndarray:
        idx = self._team_idx(team)
        return idx[self.s.active[idx]]

    def _outfield_idx(self, team: int) -> list[int]:
        return [int(i) for i in self._active_idx(team) if self.s.roles[i] != "GK"]

    def _gk(self, team: int) -> int:
        for i in self._team_idx(team):
            if self.s.roles[i] == "GK" and self.s.active[i]:
                return int(i)
        return int(self._active_idx(team)[0])

    def _frame_pos(self, team: int) -> np.ndarray:
        return to_frame(self.s.pos, self.s.direction[team])

    def _penalty_spot(self, team: int) -> np.ndarray:
        """The penalty mark `team` shoots at, in absolute coordinates."""
        return to_frame(np.array([LENGTH - PENALTY_SPOT, HALF_WIDTH]), self.s.direction[team])

    def _offside_margin(self, team: int, receiver: int, ball_abs: np.ndarray) -> float:
        """How far `receiver` is beyond the offside line as the ball is played from `ball_abs` (positive is offside)."""
        s = self.s
        P = self._frame_pos(team)
        ball_u = float(to_frame(np.asarray(ball_abs[:2], dtype=float), s.direction[team])[0])
        return float(P[receiver][0]) - offside_line(P[self._active_idx(1 - team), 0], ball_u)

    def _vmax(self) -> np.ndarray:
        s = self.s
        top = np.array([a["top_speed"] for a in s.attrs])
        stamina = np.array([a["stamina"] for a in s.attrs])
        minutes = (self.match_seconds() - s.entered_at) / 60.0
        return top * (1.0 - 0.09 * np.clip(minutes / 95.0, 0, 1.2) * (1.25 - stamina))

    def _accel(self) -> np.ndarray:
        return np.array([a["accel"] for a in self.s.attrs])

    def _edge(self, team: int) -> float:
        """The team's strength advantage over its opponent: quality gap plus home edge."""
        diff = self.clubs[team].quality - self.clubs[1 - team].quality
        return diff + (HOME_EDGE if team == 0 else -HOME_EDGE)

    def _intent(self, team: int, in_possession: bool) -> Intent:
        return intent(self.s.regimes.current, team, self.styles[team], in_possession)

    # ------------------------------------------------------------------------------------
    # Movement
    # ------------------------------------------------------------------------------------

    def _team_targets(self, ball_abs: np.ndarray, poss_team: int) -> np.ndarray:
        s = self.s
        targets = np.zeros((2 * TEAM_SIZE, 2))
        for team in (0, 1):
            frame = s.direction[team]
            idx = self._team_idx(team)
            opp_idx = self._active_idx(1 - team)
            P = to_frame(s.pos, frame)
            ball_f = to_frame(np.asarray(ball_abs[:2], dtype=float), frame)
            tf = shape_targets(
                self.sheets[team].slots,
                s.active[idx],
                ball_f,
                team == poss_team,
                self._intent(team, team == poss_team),
                self.styles[team],
                P[idx],
                P[opp_idx],
                s.run_offsets[idx],
                s.jitter[idx],
            )
            targets[idx] = to_frame(tf, frame)
        return targets

    def _urgency(self, poss_team: int) -> np.ndarray:
        u = np.zeros(2 * TEAM_SIZE)
        for team in (0, 1):
            u[self._team_idx(team)] = self._intent(team, team == poss_team).urgency
        return u

    def _advance(
        self,
        dt: float,
        ball_target: np.ndarray,
        ball_path: tuple,
        specials: dict[int, np.ndarray] | None = None,
        urgent: set[int] | None = None,
        targets: np.ndarray | None = None,
        urgency_scale: float = 1.0,
        snap: set[int] | None = None,
    ) -> None:
        """Move everyone for dt seconds and log a keyframe.

        specials override shape targets for chosen players (the receiver, pressers);
        players in snap end exactly on their special target, as far as their speed allows.
        """
        s = self.s
        dt = float(max(dt, 0.05))
        targets = self._team_targets(ball_target, s.poss_team) if targets is None else targets.copy()
        specials = specials or {}
        for i, p in specials.items():
            targets[i] = p
        vmax_full = self._vmax()
        urg = self._urgency(s.poss_team) * urgency_scale
        for i in urgent or set():
            urg[i] = URGENT
        for i in specials:
            urg[i] = max(urg[i], SPECIAL)
        vmax = vmax_full * np.clip(urg * EFFORT, 0.25, 1.0)
        # Players chasing something head straight for it; the rest drift into shape.
        arrive = np.full(len(s.pos), ARRIVE)
        for i in (urgent or set()) | set(specials):
            arrive[i] = ARRIVE_CHASING
            vmax[i] = vmax_full[i] * (URGENT if i in (urgent or set()) else SPECIAL)
        start = s.pos.copy()
        new_pos, new_vel = move(s.pos, s.vel, targets, dt, vmax, self._accel(), arrive=arrive)
        for i in snap or set():
            want = specials.get(i, new_pos[i])
            delta = want - start[i]
            # 80% of top speed on average leaves room for the smooth curve tracking.py draws
            # through the keyframes to peak below top speed.
            reach = 0.8 * vmax_full[i] * dt
            dist = float(np.hypot(*delta))
            new_pos[i] = want if dist <= reach else start[i] + delta * (reach / dist)
            new_vel[i] = (new_pos[i] - start[i]) / dt
        new_pos[~s.active] = s.pos[~s.active]
        new_vel[~s.active] = 0.0
        s.pos, s.vel = new_pos, new_vel
        # Slowly varying personal offsets, and the timing of forwards' runs against the line.
        decay = np.exp(-dt / JITTER_TIME)
        s.jitter = s.jitter * decay + s.rng.normal(0, JITTER_SD * np.sqrt(1 - decay**2), s.jitter.shape)
        rdecay = np.exp(-dt / 6.0)
        s.run_offsets = (
            RUN_OFFSET_MEAN
            + (s.run_offsets - RUN_OFFSET_MEAN) * rdecay
            + s.rng.normal(0, 1.0 * np.sqrt(1 - rdecay**2), s.run_offsets.shape)
        )
        s.t += dt
        s.ball[:2] = np.asarray(ball_target[:2], dtype=float)
        s.ball[2] = 0.0
        self._keyframe(ball_path)

    def _stoppage(
        self,
        duration: float,
        spot: np.ndarray,
        targets: np.ndarray | None = None,
        specials: dict[int, np.ndarray] | None = None,
        snap: set[int] | None = None,
        urgency_scale: float = 0.5,
    ) -> None:
        """Dead-ball time. Players settle into position, then keep moving about until play restarts,
        as they do in a real stoppage, rather than standing still."""
        s = self.s
        remaining = float(duration)
        while remaining > 0.05:
            chunk = min(remaining, STOPPAGE_STEP)
            milling = None if targets is None else targets + s.rng.normal(0.0, MILL_SD, targets.shape)
            self._advance(
                chunk,
                spot,
                ("dead", np.asarray(spot, dtype=float).copy()),
                specials=specials,
                targets=milling,
                urgency_scale=urgency_scale,
                snap=snap,
            )
            remaining -= chunk

    # ------------------------------------------------------------------------------------
    # Possession
    # ------------------------------------------------------------------------------------

    def _gain(self, i: int, cause: str) -> None:
        """Player i now has the ball."""
        s = self.s
        team = int(self.team_of[i])
        s.carrier = i
        s.last_touch_team = team
        s.ball[:2] = s.pos[i]
        if team == s.poss_team:
            return
        delayed = [o for o in s.offences if o.delayed]
        prev = s.poss_team
        s.poss_team = team
        s.possession_seq += 1
        s.offences = []
        s.last_pass = None
        s.play_pattern = "regular_play"
        s.final_third_since = None
        self._emit("possession_change", team=team, from_team=prev, cause=cause, **self._xy(s.pos[i]))
        if delayed:
            # The attack with a held flag broke down: the flag goes up and play stops for offside.
            o = delayed[0]
            self._emit(
                "offside",
                team=prev,
                player=o.player,
                pass_event=o.pass_event,
                delayed_flag=True,
                **self._xy(o.spot),
                truth=dict(margin=round(o.margin, 3)),
            )
            self._set_restart("free_kick", team, o.spot, float(s.rng.uniform(20, 35)))
            return
        u = float(to_frame(s.pos[i], s.direction[team])[0])
        opp_u = to_frame(s.pos[self._outfield_idx(1 - team)], s.direction[team])[:, 0]
        ahead = int(np.sum(opp_u > u))
        if s.regimes.on_regain(s.period, s.t, team, u, ahead, self._context(), s.rng):
            s.transition_best = (u, s.t)
            s.play_pattern = "counter"

    def _set_restart(self, kind: str, team: int, spot: np.ndarray, dead_time: float) -> None:
        s = self.s
        s.restart = Restart(kind, team, np.array(spot[:2], dtype=float), dead_time)
        s.carrier = -1
        if s.regimes.current.kind is Kind.TRANSITION:
            s.regimes.end_transition(s.period, s.t, self._context(), s.rng)

    def _raise_delayed_flag(self) -> bool:
        """An attack with a held offside flag ended without a goal: the flag goes up now."""
        s = self.s
        delayed = [o for o in s.offences if o.delayed]
        if not delayed:
            return False
        o = delayed[0]
        s.offences = []
        attacking = int(self.team_of[o.player])
        self._emit(
            "offside",
            team=attacking,
            player=o.player,
            pass_event=o.pass_event,
            delayed_flag=True,
            **self._xy(o.spot),
            truth=dict(margin=round(o.margin, 3)),
        )
        self._set_restart("free_kick", 1 - attacking, o.spot, float(s.rng.uniform(20, 35)))
        return True

    # ------------------------------------------------------------------------------------
    # A turn on the ball
    # ------------------------------------------------------------------------------------

    def _regime_tick(self) -> None:
        s = self.s
        reg = s.regimes.current
        if reg.kind is Kind.TRANSITION and s.carrier >= 0 and reg.team == s.poss_team:
            u = float(to_frame(s.ball[:2], s.direction[reg.team])[0])
            best_u, best_t = s.transition_best
            if u > best_u + 2.0:
                s.transition_best = (u, s.t)
            elif s.t - best_t > 9.0:
                # The break has stalled.
                s.regimes.end_transition(s.period, s.t, self._context(), s.rng)
        s.regimes.tick(s.period, s.t, self._context(), s.rng)

    def _pressers(self, team: int, carrier: int) -> list[int]:
        """Players of `team` who press the carrier, given pressing intensity and where the ball is."""
        s = self.s
        it = self._intent(team, False)
        idx = self._outfield_idx(team)
        d = np.linalg.norm(s.pos[idx] - s.pos[carrier], axis=1)
        order = np.argsort(d)
        # The carrier's distance from the pressing team's goal line, in that team's frame.
        ball_u_own = float(to_frame(s.pos[carrier], s.direction[team])[0])
        zone = 105.0 if it.press > 0.7 else 45.0 + 60.0 * it.press
        n = 1 + int(it.press > 0.55) + int(it.press > 0.85)
        out = []
        for k in order[:n]:
            if d[k] < 9.0 or (ball_u_own < zone and d[k] < 22.0):
                out.append(idx[k])
        return out

    def _turn(self) -> None:
        s = self.s
        if s.carrier < 0:
            self._loose_ball(s.ball[:2].copy(), aerial=False)
            return
        self._regime_tick()
        c = s.carrier
        team = int(self.team_of[c])
        opp = 1 - team
        regime = s.regimes.current
        it = self._intent(team, True)
        it_def = self._intent(opp, False)
        opp_idx = self._active_idx(opp)
        near = float(np.linalg.norm(s.pos[opp_idx] - s.pos[c], axis=1).min())

        # Time on the ball: control and look up while the nearest opponents close in.
        tob = float(s.rng.gamma(2.4, 0.60 * it.tempo)) * (0.65 if near < 4.0 else 1.0)
        tob = float(np.clip(tob, 0.35, 4.0))
        fwd = np.array([s.direction[team], 0.0])
        hold = np.clip(s.pos[c] + fwd * min(1.6, 0.7 * tob), [0.5, 0.5], [LENGTH - 0.5, WIDTH - 0.5])
        pressers = self._pressers(opp, c)
        specials = {c: hold}
        goal = np.array([0.0 if s.direction[opp] == 1 else LENGTH, HALF_WIDTH])
        for i in pressers:
            to_goal = goal - s.pos[c]
            specials[i] = s.pos[c] + to_goal / (np.hypot(*to_goal) or 1.0) * 1.2
        self._advance(tob, hold, ("carry", c), specials=specials, urgent=set(pressers), snap={c})

        d_opp = np.linalg.norm(s.pos[opp_idx] - s.pos[c], axis=1)
        k = int(np.argmin(d_opp))
        near, nearest = float(d_opp[k]), int(opp_idx[k])
        if near < 5.0 and s.roles[nearest] != "GK":
            last_i, last_t = s.last_pressure
            if not (last_i == nearest and s.t - last_t < 3.0):
                self._emit("pressure", team=opp, player=nearest, target=self._pid(c), **self._xy(s.pos[nearest]))
                s.last_pressure = (nearest, s.t)
        # Defenders jockey rather than dive in inside their own box.
        df = to_frame(s.pos[nearest], s.direction[opp])
        caution = 0.3 if in_own_box(df[0], df[1]) else 1.0
        if near < 2.0 and s.roles[nearest] != "GK" and s.rng.random() < (0.16 + 0.22 * it_def.press) * caution:
            if self._challenge(nearest, c, it_def.foul):
                return

        options = decide.evaluate(self._view(c, it), s.rng)
        if not options:
            self._clearance(c, np.array([60.0, HALF_WIDTH]))
            return
        opt = decide.choose(options, s.attrs[c]["vision"], regime.kind is Kind.CHAOS, s.rng)
        if opt.kind == "pass":
            self._pass(c, opt)
        elif opt.kind == "shot":
            self._shot(c, opt)
        elif opt.kind == "carry":
            self._carry(c, opt, it)
        elif opt.kind == "cross":
            self._cross(c, opt.target, opt.receiver)
        else:
            self._clearance(c, opt.target)

    def _view(self, c: int, it: Intent) -> decide.View:
        s = self.s
        team = int(self.team_of[c])
        P = self._frame_pos(team)
        V = s.vel * s.direction[team]
        mates = np.array([i for i in self._active_idx(team) if i != c])
        opps = self._active_idx(1 - team)
        if P[c][0] > 70.0:
            if s.final_third_since is None:
                s.final_third_since = s.t
            impatience = float(np.clip((s.t - s.final_third_since) / 35.0, 0.0, 1.0))
        else:
            s.final_third_since = None
            impatience = 0.0
        return decide.View(
            carrier=c,
            pos=P,
            vel=V,
            mates=mates,
            opps=opps,
            opp_speed=0.85 * self._vmax()[opps],
            roles=s.roles,
            attrs=s.attrs,
            gk_skill=s.attrs[self._gk(1 - team)]["gk_skill"],
            intent=it,
            style=self.styles[team],
            edge=self._edge(team),
            impatience=impatience,
        )

    # ------------------------------------------------------------------------------------
    # Duels and fouls
    # ------------------------------------------------------------------------------------

    def _challenge(self, defender: int, carrier: int, foul_shift: float, allow_foul: bool = True) -> bool:
        """A defender challenges the carrier. Returns True if the carrier's turn ends.

        allow_foul=False is a defender who stays on his feet: the challenge can't be a foul.
        """
        s = self.s
        d_team = int(self.team_of[defender])
        da, ca = s.attrs[defender], s.attrs[carrier]
        support = int(np.sum(np.linalg.norm(s.pos[self._active_idx(d_team)] - s.pos[carrier], axis=1) < 6.0)) - 1
        press = self._intent(d_team, False).press
        u_def = to_frame(s.pos[defender], s.direction[d_team])
        own_box = bool(in_own_box(u_def[0], u_def[1]))
        p_foul = models.foul_prob(da["aggression"], da["tackling"], foul_shift, own_box)
        if self._pid(defender) in s.yellow:
            p_foul *= 0.6  # a booked player is careful
        if allow_foul and s.rng.random() < p_foul:
            # Advantage leaves the carrier on the ball, so the turn carries on.
            return self._foul(defender, carrier, "challenge")
        p_win = models.tackle_win_prob(da["tackling"], ca["dribbling"], press, max(support, 0), self._edge(d_team))
        won = s.rng.random() < p_win
        self._emit(
            "tackle",
            team=d_team,
            player=defender,
            opponent=self._pid(carrier),
            outcome="won" if won else "lost",
            **self._xy(s.pos[defender]),
            truth=dict(p_win=round(p_win, 4)),
        )
        if not won:
            return False
        if own_box and s.rng.random() < officials.MISSED_BOX_FOUL_RATE:
            # The referee saw a clean tackle; VAR sees a foul and sends him to the monitor.
            self._var_missed_penalty(defender, carrier)
            return True
        near_touch = min(float(s.pos[carrier][1]), WIDTH - float(s.pos[carrier][1])) < 9.0
        if near_touch and s.rng.random() < 0.55:
            # Tackled by the touchline: the ball goes out off one of them.
            side = 0.0 if s.pos[carrier][1] < HALF_WIDTH else WIDTH
            point = np.array([float(s.pos[carrier][0]), side])
            self._advance(0.5, point, ("roll", point))
            self._ball_out(point, "touch", d_team if s.rng.random() < 0.5 else 1 - d_team)
            return True
        if s.rng.random() < 0.6:
            self._gain(defender, "tackle")
        else:
            # The ball squirts loose, sometimes over a line.
            loose = s.pos[carrier] + s.rng.normal(0, 3.5, 2)
            s.carrier = -1
            self._loose_ball(loose, aerial=False, cause="tackle", last_team=d_team)
        return True

    def _foul(self, fouler: int, victim: int, kind: str, handball: bool = False, at: np.ndarray | None = None) -> bool:
        """A foul by `fouler` on `victim`, or a handball by `fouler`.

        `at` is where the offence happened, for one penalised after the players have moved on (a
        handball VAR reviewed). Returns True if play stops, False if the referee plays advantage.
        """
        s = self.s
        f_team = int(self.team_of[fouler])
        v_team = 1 - f_team
        if at is None:
            at = s.pos[fouler] if handball else s.pos[victim]
        spot = np.array(at[:2], dtype=float)
        sv = to_frame(spot, s.direction[v_team])
        penalty = bool(in_attacking_box(sv[0], sv[1]))
        if sv[0] > 62.0 and not penalty and not handball and s.rng.random() < 0.3:
            self._emit(
                "foul",
                team=f_team,
                player=fouler,
                fouled=self._pid(victim),
                foul_type=kind,
                advantage=True,
                penalty=False,
                card=None,
                **self._xy(spot),
            )
            return False
        severity = float(np.clip(s.rng.beta(2.0, 5.0) + 0.3 * (s.attrs[fouler]["aggression"] - 0.5), 0, 1))
        reg = s.regimes.current
        tactical = reg.kind is Kind.TRANSITION and reg.team == v_team
        if handball:
            card = ("yellow" if s.rng.random() < 0.25 else None) if penalty else None
        else:
            # A keeper who brings an attacker down in the box while going for the ball is cautioned,
            # not sent off; the denial-of-a-goal-chance red is for outfielders here.
            dogso = s.roles[fouler] != "GK" and self._denies_goal_chance(victim, sv)
            card = officials.foul_card(severity, tactical, dogso, s.rng, booked=self._pid(fouler) in s.yellow)
        self._emit(
            "foul",
            team=f_team,
            player=fouler,
            fouled=None if handball else self._pid(victim),
            foul_type="handball" if handball else kind,
            advantage=False,
            penalty=penalty,
            card=card,
            **self._xy(spot),
            freeze_frame=self._freeze_frame() if penalty else None,
        )
        if card:
            self._book(fouler, card, "handball" if handball else "foul")
        if s.rng.random() < 0.04:
            # Not every caution is for a foul: dissent in the stoppage that follows.
            # Referees caution an unbooked protester; a second yellow for dissent is rare enough to leave out.
            protesters = [i for i in self._outfield_idx(int(s.rng.integers(2))) if self._pid(i) not in s.yellow]
            if protesters:
                self._book(int(s.rng.choice(protesters)), "yellow", "dissent")
        s.last_touch_team = f_team
        if penalty:
            s.time_lost += 45.0
            if not handball and self._var_review_penalty(fouler, victim):
                self._set_restart("drop_ball", f_team, s.pos[self._gk(f_team)].copy(), 5.0)
                return True
            self._set_restart("penalty", v_team, self._penalty_spot(v_team), float(s.rng.uniform(60, 100)))
            return True
        dead = float(s.rng.uniform(26, 46) + (18 if sv[0] > 70 else 0))
        if s.rng.random() < 0.06:
            stoppage = float(s.rng.uniform(45, 150))
            self._emit("injury", team=v_team, player=victim, **self._xy(s.pos[victim]))
            dead += stoppage
            s.time_lost += stoppage
        self._set_restart("free_kick", v_team, spot, dead)
        return True

    def _denies_goal_chance(self, victim: int, victim_frame_pos: np.ndarray) -> bool:
        """DOGSO, roughly: through on goal centrally, close, no covering defender but the keeper."""
        s = self.s
        u, v = float(victim_frame_pos[0]), float(victim_frame_pos[1])
        if u < 78.0 or abs(v - HALF_WIDTH) > 14.0 or float(dist_to_goal(u, v)) > 22.0:
            return False
        v_team = int(self.team_of[victim])
        opp_u = to_frame(s.pos[self._outfield_idx(1 - v_team)], s.direction[v_team])[:, 0]
        return int(np.sum(opp_u > u)) == 0

    def _book(self, i: int, card: str, reason: str) -> None:
        s = self.s
        pid = self._pid(i)
        team = int(self.team_of[i])
        if card == "yellow":
            s.yellow[pid] = s.yellow.get(pid, 0) + 1
            if s.yellow[pid] >= 2:
                self._emit("card", team=team, player=i, card="second_yellow", reason=reason)
                self._send_off(i)
                return
            self._emit("card", team=team, player=i, card="yellow", reason=reason)
            return
        self._emit("card", team=team, player=i, card="red", reason=reason)
        self._send_off(i)

    def _send_off(self, i: int) -> None:
        s = self.s
        was_keeper = s.roles[i] == "GK"
        s.active[i] = False
        s.time_lost += 40.0
        s.pos[i] = np.array([LENGTH / 2, -1.0])
        s.vel[i] = 0.0
        if s.carrier == i:
            s.carrier = -1
        if was_keeper:
            self._replace_keeper(int(self.team_of[i]), i)

    def _replace_keeper(self, team: int, gk_slot: int) -> None:
        """A sent-off keeper is replaced: the reserve comes on for an outfielder, or an outfielder
        takes the gloves if no substitutions are left. The team plays on with ten either way."""
        s = self.s
        outfield = self._outfield_idx(team)
        if not outfield:
            return
        goal = np.array([1.5 if s.direction[team] == 1 else LENGTH - 1.5, HALF_WIDTH])
        reserves = [pid for pid in s.bench[team] if self.players[pid].role == "GK"]
        if reserves and s.subs_made[team] < MAX_SUBS:
            off = max(outfield, key=lambda k: self.slots[k].row)
            pid_on, pid_off = reserves[0], s.occupants[off]
            s.bench[team].remove(pid_on)
            s.active[off] = False
            s.pos[off] = np.array([LENGTH / 2, -1.0])
            s.occupants[gk_slot] = pid_on
            s.attrs[gk_slot] = self._attrs_of(pid_on)
            s.entered_at[gk_slot] = self.match_seconds()
            s.subs_made[team] += 1
            self._emit(
                "substitution",
                team=team,
                player_off=pid_off,
                player_on=pid_on,
                half_time=False,
                reason="goalkeeper_sent_off",
            )
        else:
            stand_in = min(outfield, key=lambda k: self.slots[k].row)
            s.occupants[gk_slot] = s.occupants[stand_in]
            s.attrs[gk_slot] = s.attrs[stand_in]
            s.entered_at[gk_slot] = s.entered_at[stand_in]
            s.active[stand_in] = False
            s.pos[stand_in] = np.array([LENGTH / 2, -1.0])
        s.active[gk_slot] = True
        s.pos[gk_slot] = goal
        s.vel[gk_slot] = 0.0
        s.occupancy_version = len(self.occupancy)
        self.occupancy.append(tuple(s.occupants))

    # ------------------------------------------------------------------------------------
    # Passing
    # ------------------------------------------------------------------------------------

    def _pass(self, c: int, opt: decide.Option, pass_type: str = "open_play", body_part: str = "foot") -> None:
        s = self.s
        team = int(self.team_of[c])
        receiver = opt.receiver
        start = s.pos[c].copy()
        r_abs = to_frame(opt.target, s.direction[team])
        det = opt.detail
        flight = float(det["flight"])
        v0 = float(det["v0"])
        P = self._frame_pos(team)
        opp_f = P[self._active_idx(1 - team)]
        recv_u = float(P[receiver][0])
        margin = self._offside_margin(team, receiver, start)
        offside_applies = pass_type not in ("throw_in", "goal_kick", "corner", "kick_off")
        offside_pos = offside_applies and margin > 0
        recv_spot = s.pos[receiver].copy()
        # A pass that finds a team-mate in an offside position carries the freeze frame offside is judged on.
        ff = self._freeze_frame() if offside_pos else None
        complete = s.rng.random() < opt.p_success
        base = dict(
            recipient=self._pid(receiver),
            height="high" if opt.lofted else "ground",
            pass_type=pass_type,
            body_part=body_part,
            cross=False,
            through_ball=opt.through,
            length=round(float(det["dist"]), 2),
            speed_kmh=round(v0 * 3.6, 1),
            under_pressure=bool(models.passer_pressure(P[c], opp_f) > 0.5),
            **self._xy(start),
        )
        truth = dict(
            p_complete=round(opt.p_success, 4),
            regime=s.regimes.current.label,
            offside_margin=round(margin, 3) if offside_applies and recv_u > LENGTH / 2 else None,
        )
        path = ("pass", start, r_abs, v0, opt.lofted)
        if complete and offside_pos:
            promising = float(dist_to_goal(*opt.target)) < 36.0
            call = officials.assistant_offside_call(margin, promising, s.rng)
            if call.flag:
                idx = self._emit(
                    "pass",
                    team=team,
                    player=c,
                    outcome="offside",
                    **base,
                    **self._end_xy(r_abs),
                    truth=truth,
                    freeze_frame=ff,
                )
                self._advance(flight, r_abs, path, specials={receiver: r_abs}, urgent={receiver})
                self._emit(
                    "offside",
                    team=team,
                    player=receiver,
                    pass_event=idx,
                    delayed_flag=False,
                    **self._xy(recv_spot),
                    truth=dict(margin=round(margin, 3)),
                )
                s.last_touch_team = team
                self._set_restart("free_kick", 1 - team, recv_spot, float(s.rng.uniform(20, 35)))
                return
            idx = self._emit(
                "pass",
                team=team,
                player=c,
                outcome="complete",
                **base,
                **self._end_xy(r_abs),
                truth=truth,
                freeze_frame=ff,
            )
            s.offences.append(OffsideOffence(idx, receiver, margin, recv_spot, delayed=call.delayed))
            self._complete_pass(c, receiver, r_abs, path, flight, idx)
            return
        if complete:
            idx = self._emit(
                "pass", team=team, player=c, outcome="complete", **base, **self._end_xy(r_abs), truth=truth
            )
            self._complete_pass(c, receiver, r_abs, path, flight, idx)
            return
        self._failed_pass(c, opt, base, truth, start, r_abs, v0, flight)

    def _complete_pass(self, c: int, receiver: int, r_abs: np.ndarray, path: tuple, flight: float, idx: int) -> None:
        s = self.s
        self._advance(flight, r_abs, path, specials={receiver: r_abs}, urgent={receiver}, snap={receiver})
        s.last_pass = (idx, c, receiver)
        self._gain(receiver, "pass")

    def _failed_pass(
        self,
        c: int,
        opt: decide.Option,
        base: dict,
        truth: dict,
        start: np.ndarray,
        r_abs: np.ndarray,
        v0: float,
        flight: float,
    ) -> None:
        s = self.s
        team = int(self.team_of[c])
        det = opt.detail
        opps = self._active_idx(1 - team)
        weights = np.array([2.0 * det["lane"], 1.2 * det["recv_press"], 0.25 + 0.35 * opt.lofted])
        wide = min(float(r_abs[1]), WIDTH - float(r_abs[1])) < 9.0
        if wide:
            # Passes to the flanks that go wrong tend to run out of play.
            weights[2] *= 2.5
        mode = int(s.rng.choice(3, p=weights / weights.sum()))
        s.last_touch_team = team
        s.carrier = -1
        if mode == 0 and det["interceptor"] >= 0:
            k = int(opps[det["interceptor"]])
            frac = float(np.clip(det["lane_s"], 0.05, 1.0))
            point = start + frac * (r_abs - start)
            self._emit("pass", team=team, player=c, outcome="incomplete", **base, **self._end_xy(point), truth=truth)
            self._advance(
                max(frac * flight, 0.2),
                point,
                ("pass", start, point, v0, opt.lofted),
                specials={k: point},
                urgent={k},
                snap={k},
            )
            if min(float(point[1]), WIDTH - float(point[1])) < 6.0 and s.rng.random() < 0.5:
                # Stretched for by the touchline: it goes out off the defender.
                side = 0.0 if point[1] < HALF_WIDTH else WIDTH
                self._ball_out(np.array([float(point[0]), side]), "touch", 1 - team)
                return
            if s.rng.random() < 0.22:
                # A block or a stretch rather than a clean interception: the ball runs loose.
                self._emit("block", team=1 - team, player=k, **self._xy(point))
                self._loose_ball(point + s.rng.normal(0, 4.0, 2), aerial=False, last_team=1 - team)
                return
            self._emit("interception", team=1 - team, player=k, **self._xy(point))
            self._gain(k, "interception")
            return
        if mode == 1:
            k = int(opps[int(np.argmin(np.linalg.norm(s.pos[opps] - r_abs, axis=1)))])
            self._emit("pass", team=team, player=c, outcome="incomplete", **base, **self._end_xy(r_abs), truth=truth)
            self._advance(
                flight,
                r_abs,
                ("pass", start, r_abs, v0, opt.lofted),
                specials={k: r_abs, opt.receiver: r_abs},
                urgent={k, opt.receiver},
                snap={k},
            )
            if s.rng.random() < 0.35:
                # Contested on arrival: one of them wins the challenge, but the ball ends up loose,
                # sometimes off one of them and out.
                p_k = models.ground_duel_prob(s.attrs[k], s.attrs[opt.receiver])
                winner, loser = (k, opt.receiver) if s.rng.random() < p_k else (opt.receiver, k)
                self._emit(
                    "duel",
                    team=int(self.team_of[winner]),
                    player=winner,
                    opponent=self._pid(loser),
                    duel_type="ground",
                    outcome="won",
                    **self._xy(r_abs),
                    truth=dict(p_win=round(p_k if winner == k else 1.0 - p_k, 4)),
                )
                self._loose_ball(r_abs + s.rng.normal(0, 3.5, 2), aerial=False, last_team=int(s.rng.integers(2)))
                return
            self._emit("ball_recovery", team=1 - team, player=k, **self._xy(r_abs))
            self._gain(k, "recovery")
            return
        direction = (r_abs - start) / (np.hypot(*(r_abs - start)) or 1.0)
        end = r_abs + direction * float(s.rng.uniform(4.0, 14.0)) + s.rng.normal(0, 4.0, 2)
        if wide:
            end[1] += (-1.0 if r_abs[1] < HALF_WIDTH else 1.0) * float(s.rng.uniform(2.0, 8.0))
        out = exit_point(start, end)
        if out is not None:
            point, line = out
            self._emit("pass", team=team, player=c, outcome="out", **base, **self._end_xy(point), truth=truth)
            t_out = flight * float(np.hypot(*(point - start)) / max(np.hypot(*(r_abs - start)), 1e-6))
            self._advance(max(t_out, 0.3), point, ("pass", start, point, v0, opt.lofted))
            self._ball_out(point, line, team)
            return
        self._emit("pass", team=team, player=c, outcome="incomplete", **base, **self._end_xy(end), truth=truth)
        self._advance(flight * 1.2, end, ("pass", start, end, v0, opt.lofted))
        self._loose_ball(end, aerial=opt.lofted, cause="loose")

    def _ball_out(self, point: np.ndarray, line: str, last_team: int) -> None:
        """The ball crossed a line: work out the restart."""
        s = self.s
        p = np.array([np.clip(point[0], 0.0, LENGTH), np.clip(point[1], 0.0, WIDTH)])
        if self._raise_delayed_flag():
            return
        if line == "touch":
            self._emit("ball_out", restart="throw_in", last_touch_team=last_team, **self._xy(p))
            self._set_restart(
                "throw_in", 1 - last_team, p, float(np.clip(s.rng.lognormal(np.log(15.5), 0.35), 6.0, 40.0))
            )
            return
        # Goal line: the team attacking towards x = 105 defends x = 0.
        defending = 0 if (p[0] < LENGTH / 2) == (s.direction[0] == 1) else 1
        if last_team == defending:
            corner = np.array([0.0 if p[0] < LENGTH / 2 else LENGTH, 0.0 if p[1] < HALF_WIDTH else WIDTH])
            self._emit("ball_out", restart="corner", last_touch_team=last_team, **self._xy(p))
            self._set_restart(
                "corner", 1 - defending, corner, float(np.clip(s.rng.lognormal(np.log(40.0), 0.25), 22.0, 80.0))
            )
            return
        gx = 5.5 if p[0] < LENGTH / 2 else LENGTH - 5.5
        self._emit("ball_out", restart="goal_kick", last_touch_team=last_team, **self._xy(p))
        self._set_restart(
            "goal_kick",
            defending,
            np.array([gx, HALF_WIDTH + (3.0 if p[1] > HALF_WIDTH else -3.0)]),
            float(np.clip(s.rng.lognormal(np.log(33.0), 0.3), 14.0, 70.0)),
        )

    # ------------------------------------------------------------------------------------
    # Loose balls, carries, clearances
    # ------------------------------------------------------------------------------------

    def _loose_ball(self, point: np.ndarray, aerial: bool, cause: str = "loose", last_team: int | None = None) -> None:
        """Players race for a loose ball. If it has rolled over a line, it's out of play."""
        s = self.s
        s.carrier = -1
        if last_team is not None and not (0.0 <= point[0] <= LENGTH and 0.0 <= point[1] <= WIDTH):
            out = exit_point(s.ball[:2].copy(), np.asarray(point, dtype=float))
            if out is not None:
                self._advance(0.6, out[0], ("roll", out[0]))
                self._ball_out(out[0], out[1], last_team)
                return
        if last_team is not None and min(float(point[1]), WIDTH - float(point[1])) < 3.0 and s.rng.random() < 0.3:
            side = 0.0 if point[1] < HALF_WIDTH else WIDTH
            edge = np.array([float(np.clip(point[0], 0.5, LENGTH - 0.5)), side])
            self._advance(0.8, edge, ("roll", edge))
            self._ball_out(edge, "touch", last_team)
            return
        point = np.clip(point, [0.3, 0.3], [LENGTH - 0.3, WIDTH - 0.3])
        idx = np.where(s.active)[0]
        vmax = self._vmax()[idx]
        arrival = np.linalg.norm(s.pos[idx] - point, axis=1) / (0.85 * vmax) + 0.3 + s.rng.normal(0, 0.2, len(idx))
        for k, i in enumerate(idx):
            if s.roles[i] == "GK":
                fp = to_frame(point, s.direction[int(self.team_of[i])])
                if in_own_box(fp[0], fp[1]):
                    arrival[k] -= 0.15 if aerial else 0.3
        order = np.argsort(arrival)
        first = int(idx[order[0]])
        t_arrive = float(np.clip(arrival[order[0]], 0.3, 4.0))
        rival_k = next((k for k in order[1:] if self.team_of[idx[k]] != self.team_of[first]), None)
        if rival_k is not None:
            rival = int(idx[rival_k])
            gap = float(arrival[rival_k] - arrival[order[0]])
            if aerial or gap < 0.35:
                a, b = s.attrs[first], s.attrs[rival]
                if aerial:
                    p = models.aerial_win_prob(a["heading"], a["height"], b["heading"], b["height"])
                    duel_type = "aerial"
                else:
                    p = models.ground_duel_prob(a, b)
                    duel_type = "ground"
                p = float(np.clip(p + 0.5 * min(gap, 0.5), 0.05, 0.95))
                winner = first if s.rng.random() < p else rival
                loser = rival if winner == first else first
                self._advance(
                    t_arrive,
                    point,
                    ("roll", point),
                    specials={first: point, rival: point},
                    urgent={first, rival},
                    snap={winner},
                )
                foul_team = int(self.team_of[loser])
                shift = self._intent(foul_team, foul_team == s.poss_team).foul
                lf = to_frame(s.pos[loser], s.direction[foul_team])
                p_foul = 0.45 * models.foul_prob(
                    s.attrs[loser]["aggression"], s.attrs[loser]["tackling"], shift, bool(in_own_box(lf[0], lf[1]))
                )
                if self._pid(loser) in s.yellow:
                    p_foul *= 0.6
                if in_own_box(lf[0], lf[1]):
                    p_foul *= 0.5  # nobody wants to give away a penalty in an aerial challenge
                if s.roles[loser] == "GK":
                    p_foul *= 0.3
                if s.rng.random() < p_foul:
                    if self._foul(loser, winner, "aerial" if aerial else "challenge"):
                        return
                self._emit(
                    "duel",
                    team=int(self.team_of[winner]),
                    player=winner,
                    opponent=self._pid(loser),
                    duel_type=duel_type,
                    outcome="won",
                    **self._xy(point),
                    truth=dict(p_win=round(p if winner == first else 1.0 - p, 4)),
                )
                if aerial and s.roles[winner] != "GK":
                    wf = to_frame(point, s.direction[int(self.team_of[winner])])
                    if wf[0] < 35.0 and s.rng.random() < 0.6:
                        # A defender under a high ball in his own third heads it away.
                        self._headed_clearance(winner, point)
                        return
                    self._header_on(winner, point)
                    return
                self._gain(winner, "duel")
                return
        self._advance(t_arrive, point, ("roll", point), specials={first: point}, urgent={first}, snap={first})
        self._emit("ball_recovery", team=int(self.team_of[first]), player=first, **self._xy(point))
        self._gain(first, cause if cause != "loose" else "recovery")

    def _headed_clearance(self, i: int, point: np.ndarray) -> None:
        s = self.s
        team = int(self.team_of[i])
        pf = to_frame(point, s.direction[team])
        if in_own_box(pf[0], pf[1]) and s.rng.random() < 0.18:
            # Headed behind for a corner.
            behind = to_frame(
                np.array([0.0, HALF_WIDTH + np.sign(pf[1] - HALF_WIDTH + 1e-6) * s.rng.uniform(8, 25)]),
                s.direction[team],
            )
            self._emit("clearance", team=team, player=i, body_part="head", **self._xy(point), **self._end_xy(behind))
            self._advance(0.8, behind, ("pass", point, behind, 14.0, True))
            self._ball_out(behind, "goal", team)
            return
        if s.rng.random() < 0.3:
            clear_f = np.array([s.rng.uniform(25.0, 45.0), -2.0 if pf[1] < HALF_WIDTH else WIDTH + 2.0])
        else:
            clear_f = np.array([s.rng.uniform(32.0, 55.0), HALF_WIDTH + s.rng.normal(0, 22)])
        clear_abs = to_frame(clear_f, s.direction[team])
        out = exit_point(point, clear_abs)
        self._emit(
            "clearance",
            team=team,
            player=i,
            body_part="head",
            **self._xy(point),
            **self._end_xy(out[0] if out else clear_abs),
        )
        s.last_touch_team = team
        s.carrier = -1
        if out is not None:
            self._advance(1.3, out[0], ("pass", point, out[0], 15.0, True))
            self._ball_out(out[0], out[1], team)
            return
        self._advance(1.6, clear_abs, ("pass", point, clear_abs, 15.0, True))
        self._loose_ball(clear_abs, aerial=True, cause="clearance")

    def _header_on(self, i: int, point: np.ndarray) -> None:
        """A won header in open play goes to a team-mate or into space."""
        s = self.s
        team = int(self.team_of[i])
        mates = [int(j) for j in self._active_idx(team) if j != i]
        d = np.linalg.norm(s.pos[mates] - point, axis=1)
        # Heading on to a team-mate who is clearly offside is avoided, as it is with a pass.
        P = self._frame_pos(team)
        o_line = offside_line(P[self._active_idx(1 - team), 0], float(to_frame(point, s.direction[team])[0]))
        near = [
            m
            for m, dist in zip(mates, d, strict=True)
            if 6.0 < dist < 22.0 and P[m][0] - o_line <= decide.CLEARLY_OFFSIDE
        ]
        s.last_touch_team = team
        if near and s.rng.random() < 0.55:
            j = int(s.rng.choice(near))
            # Winning the header wins the ball, so a flag held against the other side goes up here.
            self._gain(i, "duel")
            if s.restart is not None:
                return
            self._pass(i, self._header_option(i, j), body_part="head")
            return
        end = np.clip(point + s.rng.normal(0, 8.0, 2), [0.5, 0.5], [LENGTH - 0.5, WIDTH - 0.5])
        self._advance(1.0, end, ("pass", point, end, 11.0, True))
        self._loose_ball(end, aerial=False)

    def _header_option(self, i: int, j: int) -> decide.Option:
        """A headed pass from i to team-mate j, scored with the same completion model as any other pass."""
        s = self.s
        team = int(self.team_of[i])
        P = self._frame_pos(team)
        opps = self._active_idx(1 - team)
        opp_pos, opp_speed = P[opps], 0.85 * self._vmax()[opps]
        me, ends = P[i], P[j][None, :]
        dist = max(float(np.hypot(*(ends[0] - me))), 1.0)
        v0 = 11.0
        flight = dist / (0.78 * v0)
        lofted = np.array([True])
        lane, interceptor, lane_s = models.lane_risk(me, ends, opp_pos, opp_speed, np.array([dist / flight]), lofted)
        recv_press = models.receiver_pressure(ends, opp_pos, opp_speed, np.array([flight]))
        into_box = bool(in_attacking_box(ends[0, 0], ends[0, 1])) and not bool(in_attacking_box(me[0], me[1]))
        p = models.pass_completion(
            np.array([dist]),
            lofted,
            lane,
            recv_press,
            models.passer_pressure(me, opp_pos),
            s.attrs[i]["heading"],
            np.array([s.attrs[j]["first_touch"]]),
            self._intent(team, True).retention,
            np.array([into_box]),
            edge=self._edge(team),
        )
        return decide.Option(
            "pass",
            0.0,
            ends[0].copy(),
            receiver=j,
            lofted=True,
            p_success=float(p[0]),
            detail=dict(
                lane=float(lane[0]),
                interceptor=int(interceptor[0]),
                lane_s=float(lane_s[0]),
                recv_press=float(recv_press[0]),
                v0=v0,
                flight=flight,
                dist=dist,
                into_box=into_box,
            ),
        )

    def _carry(self, c: int, opt: decide.Option, it: Intent) -> None:
        s = self.s
        team = int(self.team_of[c])
        start = s.pos[c].copy()
        target = to_frame(opt.target, s.direction[team])
        length = float(np.hypot(*(target - start)))
        speed = min(0.82 * float(self._vmax()[c]), 3.8 + 2.4 * it.carry)
        duration = max(length / speed, 0.4)
        self._emit(
            "carry",
            team=team,
            player=c,
            **self._xy(start),
            **self._end_xy(target),
            duration=round(duration, 2),
            truth=dict(p_keep=round(opt.p_success, 4)),
        )
        pressers = self._pressers(1 - team, c)
        specials = {c: target}
        for i in pressers:
            specials[i] = target
        self._advance(duration, target, ("carry", c), specials=specials, urgent=set(pressers) | {c}, snap={c})
        s.ball[:2] = s.pos[c]
        if s.rng.random() > opt.p_success:
            opp_idx = self._outfield_idx(1 - team)
            d = np.linalg.norm(s.pos[opp_idx] - s.pos[c], axis=1)
            if float(d.min()) < 6.0:
                k = opp_idx[int(np.argmin(d))]
                # The defender steps in to close the carrier down.
                here = s.pos[c].copy()
                close = here + (s.pos[k] - here) / (float(d.min()) or 1.0) * 0.9
                self._advance(0.5, here, ("carry", c), specials={k: close, c: here}, urgent={k}, snap={k, c})
                kf = to_frame(s.pos[k], s.direction[1 - team])
                # In his own box the defender usually stays on his feet rather than risk a penalty.
                clean = bool(in_own_box(kf[0], kf[1])) and s.rng.random() < 0.6
                self._challenge(k, c, self._intent(1 - team, False).foul + 0.3, allow_foul=not clean)

    def _clearance(self, c: int, target_frame: np.ndarray) -> None:
        s = self.s
        team = int(self.team_of[c])
        start = s.pos[c].copy()
        landing = to_frame(target_frame, s.direction[team])
        dist = float(np.hypot(*(landing - start)))
        v0 = float(np.clip(20.0 + s.rng.normal(0, 2.5), 15.0, 28.0))
        flight = dist / (0.78 * v0)
        s.last_touch_team = team
        s.carrier = -1
        out = exit_point(start, landing)
        self._emit(
            "clearance",
            team=team,
            player=c,
            body_part="foot",
            **self._xy(start),
            **self._end_xy(out[0] if out else landing),
        )
        if out is not None:
            point, line = out
            self._advance(
                flight * float(np.hypot(*(point - start))) / max(dist, 1e-6), point, ("pass", start, point, v0, True)
            )
            self._ball_out(point, line, team)
            return
        self._advance(flight, landing, ("pass", start, landing, v0, True))
        self._loose_ball(landing, aerial=True, cause="clearance")

    # ------------------------------------------------------------------------------------
    # Shooting
    # ------------------------------------------------------------------------------------

    def _shot(
        self,
        c: int,
        opt: decide.Option | None,
        header: bool = False,
        shot_type: str = "open_play",
        xg_override: float | None = None,
        blockers: int | None = None,
    ) -> None:
        s = self.s
        team = int(self.team_of[c])
        frame = s.direction[team]
        P = self._frame_pos(team)
        me = P[c].copy()
        opp_out = self._outfield_idx(1 - team)
        opp_f = P[opp_out]
        mask = decide.cone_mask(me, opp_f)
        cone = int(mask.sum()) if blockers is None else blockers
        d_goal = float(dist_to_goal(me[0], me[1]))
        a = s.attrs[c]
        gk = self._gk(1 - team)
        if xg_override is not None:
            xg = xg_override
        elif opt is not None and "xg" in opt.detail:
            xg = float(opt.detail["xg"])
        else:
            xg = models.expected_goal(
                me[0],
                me[1],
                header,
                models.passer_pressure(me, opp_f),
                cone,
                False,
                a["finishing"],
                s.attrs[gk]["gk_skill"],
                edge=self._edge(team),
            )
        block_zone = decide.cone_mask(me, opp_f, reach=2.8)
        near_blockers = int(np.sum(block_zone & (np.linalg.norm(opp_f - me, axis=1) < 12.0)))
        if shot_type == "penalty":
            probs = dict(blocked=0.0, off_target=0.09, saved=max(0.91 - xg, 0.0), goal=xg)
        else:
            probs = models.shot_outcome_probs(xg, d_goal, near_blockers, a["finishing"], header)
        keys = list(probs)
        pv = np.array([probs[k] for k in keys])
        outcome = keys[int(s.rng.choice(len(keys), p=pv / pv.sum()))]
        in_front = block_zone.copy()
        if not in_front.any() and len(opp_f):
            rel = opp_f - me
            in_front = (np.linalg.norm(rel, axis=1) < 4.0) & (rel[:, 0] > 0.0)
        if outcome == "blocked" and not in_front.any():
            outcome = "off_target"
        speed = models.shot_speed(d_goal, header, shot_type == "penalty", s.rng)
        if outcome in ("goal", "saved"):
            end_f = np.array([LENGTH, HALF_WIDTH + s.rng.uniform(-3.3, 3.3)])
            z = float(s.rng.uniform(0.1, 2.2))
        elif outcome == "off_target":
            if s.rng.random() < 0.45:
                end_f = np.array([LENGTH, HALF_WIDTH + s.rng.choice([-1, 1]) * s.rng.uniform(3.8, 9.0)])
                z = float(s.rng.uniform(0.1, 2.0))
            else:
                end_f = np.array([LENGTH, HALF_WIDTH + s.rng.uniform(-4.5, 4.5)])
                z = float(s.rng.uniform(2.5, 6.0))
        else:
            end_f = me.copy()
            z = 0.4
        blocker = None
        if outcome == "blocked":
            candidates = [opp_out[k] for k in np.where(in_front)[0]]
            blocker = min(candidates, key=lambda i: float(np.hypot(*(P[i] - me))))
            end_f = P[blocker].copy()
        end_abs = to_frame(end_f, frame)
        start = s.pos[c].copy()
        foot = self.players[self._pid(c)].foot
        if header:
            body = "head"
        else:
            strong = s.rng.random() < 0.8
            body = (
                ("right_foot" if foot == "R" else "left_foot")
                if strong
                else ("left_foot" if foot == "R" else "right_foot")
            )
        shot_idx = self._emit(
            "shot",
            team=team,
            player=c,
            outcome=outcome,
            body_part=body,
            shot_type=shot_type,
            play_pattern=s.play_pattern,
            set_piece=self._set_piece_phase(),
            speed_kmh=round(speed, 1),
            distance=round(d_goal, 2),
            goalkeeper=self._pid(gk),
            **self._xy(start),
            **self._end_xy(end_abs),
            end_z=round(z, 2),
            freeze_frame=self._freeze_frame(),
            truth=dict(
                xg=round(xg, 4), regime=s.regimes.current.label, probs={k: round(v, 4) for k, v in probs.items()}
            ),
        )
        s.last_touch_team = team
        s.carrier = -1
        s.final_third_since = None
        in_transition = s.regimes.current.kind is Kind.TRANSITION and s.regimes.current.team == team
        flight = max(float(np.hypot(*(end_abs - start))) / (speed / 3.6 * 0.92), 0.15)

        if outcome == "blocked":
            assert blocker is not None
            block_pt = s.pos[blocker].copy()
            self._advance(0.25, block_pt, ("shot", start, block_pt, speed, 0.6))
            self._emit("block", team=1 - team, player=blocker, **self._xy(block_pt))
            if in_transition:
                s.regimes.end_transition(s.period, s.t, self._context(), s.rng)
            bf = to_frame(block_pt, s.direction[1 - team])
            if in_own_box(bf[0], bf[1]) and officials.arm_contact(s.rng, close_range=near_blockers > 0):
                self._handball_claim(blocker, c, block_pt)
                return
            if s.rng.random() < 0.5:
                out_f = np.array([LENGTH, HALF_WIDTH + s.rng.choice([-1, 1]) * s.rng.uniform(6, 20)])
                self._ball_out(to_frame(out_f, frame), "goal", 1 - team)
            else:
                self._loose_ball(block_pt + s.rng.normal(0, 5.0, 2), aerial=False, last_team=1 - team)
            return
        self._advance(flight, end_abs, ("shot", start, end_abs, speed, z))
        if in_transition:
            s.regimes.end_transition(s.period, s.t, self._context(), s.rng)
        if outcome == "goal":
            self._goal(team, c, shot_idx, deflector=self._deflector(me, P, opp_out, cone), shot_type=shot_type)
            return
        if outcome == "off_target" and cone > 0 and shot_type == "open_play" and s.rng.random() < 0.02 * cone:
            # Going wide until it came off a defender and went in.
            deflector = self._deflector(me, P, opp_out, cone, always=True)
            if deflector is not None:
                self._goal(team, deflector, shot_idx, deflector=None, shot_type=shot_type, own_goal=True, header=False)
                return
        if outcome == "saved":
            held = s.rng.random() < 0.35 + 0.35 * s.attrs[gk]["handling"]
            self._emit(
                "goalkeeper",
                team=1 - team,
                player=gk,
                action="save",
                outcome="held" if held else "parried",
                **self._xy(s.pos[gk]),
            )
            if self._raise_delayed_flag():
                return
            if held:
                self._gain(gk, "save")
            elif s.rng.random() < 0.55:
                out_f = np.array([LENGTH, HALF_WIDTH + s.rng.choice([-1, 1]) * s.rng.uniform(5, 15)])
                self._ball_out(to_frame(out_f, frame), "goal", 1 - team)
            else:
                rebound_f = np.array([LENGTH - s.rng.uniform(3, 12), HALF_WIDTH + s.rng.normal(0, 8)])
                self._loose_ball(to_frame(rebound_f, frame), aerial=False, last_team=1 - team)
            return
        if s.rng.random() < 0.07:
            self._emit("woodwork", team=team, player=c, **self._xy(end_abs))
            rebound_f = np.array([LENGTH - s.rng.uniform(4, 14), HALF_WIDTH + s.rng.normal(0, 7)])
            self._loose_ball(to_frame(rebound_f, frame), aerial=False)
            return
        self._ball_out(end_abs, "goal", team)

    def _set_piece_phase(self) -> bool:
        """True within 15 seconds of a corner or free kick, or 8 of a throw-in (penalties excluded).

        A throw-in starts most attacks down the flanks; only the shorter window catches goals that
        came from the throw itself rather than the play that followed it.
        """
        s = self.s
        window = {"corner": 15.0, "free_kick": 15.0, "throw_in": 8.0}.get(s.play_pattern)
        return window is not None and s.t - s.restart_at <= window

    def _deflector(
        self, me: np.ndarray, P: np.ndarray, opp_out: list[int], cone: int, always: bool = False
    ) -> int | None:
        """For a goal: the defender who got a touch on the way in, if anyone did."""
        s = self.s
        if cone == 0 or not opp_out or (not always and s.rng.random() >= 1.0 - np.exp(-0.40 * cone)):
            return None
        to_goal = np.array([LENGTH, HALF_WIDTH]) - me
        norm = float(np.hypot(*to_goal)) or 1.0

        def path_dist(i: int) -> float:
            rel = P[i] - me
            if float(rel @ to_goal) <= 0.0:
                return 99.0
            return float(abs(rel[0] * to_goal[1] - rel[1] * to_goal[0]) / norm)

        best = min(opp_out, key=path_dist)
        return best if path_dist(best) < 3.0 else None

    def _handball_claim(self, defender: int, attacker: int, spot: np.ndarray) -> None:
        """The ball struck a defender's arm in their own box. VAR checks while play is stopped."""
        s = self.s
        d_team = int(self.team_of[defender])
        a_team = 1 - d_team
        unnatural = officials.arm_unnatural(s.rng)
        on_field = officials.referee_awards_handball(unnatural, s.rng)
        start_idx = self._emit(
            "var_check",
            status="started",
            check="penalty",
            incident="handball",
            on_field_decision="penalty" if on_field else "no_penalty",
            subject=self._pid(defender),
            **self._xy(spot),
            freeze_frame=self._freeze_frame(),
            truth=dict(arm_unnatural=unnatural),
        )
        duration = float(np.clip(s.rng.lognormal(np.log(75.0), 0.35), 35.0, 200.0))
        overturn = officials.var_corrects(on_field, unnatural, s.rng)
        final = (not on_field) if overturn else on_field
        s.time_lost += duration
        self._stoppage(duration, spot, urgency_scale=0.4)
        self._emit(
            "var_check",
            status="complete",
            check="penalty",
            incident="handball",
            decision="penalty" if final else "no_penalty",
            overturned=overturn,
            on_field_review=overturn,
            related=start_idx,
            subject=self._pid(defender),
            **self._xy(spot),
            truth=dict(arm_unnatural=unnatural),
        )
        if final:
            # Penalised where the ball struck the arm; the defender may have moved during the check.
            self._foul(defender, attacker, "handball", handball=True, at=spot)
            return
        # No penalty: the ball had gone out off the defender, so play restarts with a corner.
        corner_f = np.array([LENGTH, HALF_WIDTH + s.rng.choice([-1, 1]) * s.rng.uniform(6, 20)])
        self._ball_out(to_frame(corner_f, s.direction[a_team]), "goal", d_team)

    def _var_review_penalty(self, fouler: int, victim: int) -> bool:
        """Every penalty is checked. Returns True if VAR overturns it."""
        s = self.s
        spot = s.pos[victim].copy()
        start_idx = self._emit(
            "var_check",
            status="started",
            check="penalty",
            incident="foul",
            on_field_decision="penalty",
            subject=self._pid(fouler),
            **self._xy(spot),
        )
        duration = float(np.clip(s.rng.lognormal(np.log(40.0), 0.3), 20.0, 120.0))
        s.time_lost += duration
        overturn = bool(s.rng.random() < 0.06)
        self._stoppage(duration, spot, urgency_scale=0.4)
        self._emit(
            "var_check",
            status="complete",
            check="penalty",
            incident="foul",
            decision="no_penalty" if overturn else "penalty",
            overturned=overturn,
            on_field_review=overturn,
            related=start_idx,
            subject=self._pid(fouler),
            **self._xy(spot),
        )
        return overturn

    def _var_missed_penalty(self, defender: int, attacker: int) -> None:
        """VAR recommends a review of a tackle in the box the referee let go; most become penalties."""
        s = self.s
        spot = s.pos[attacker].copy()
        start_idx = self._emit(
            "var_check",
            status="started",
            check="penalty",
            incident="foul",
            on_field_decision="no_penalty",
            subject=self._pid(defender),
            **self._xy(spot),
            freeze_frame=self._freeze_frame(),
        )
        duration = float(np.clip(s.rng.lognormal(np.log(95.0), 0.3), 45.0, 220.0))
        s.time_lost += duration
        self._stoppage(duration, spot, urgency_scale=0.4)
        award = bool(s.rng.random() < 0.85)
        self._emit(
            "var_check",
            status="complete",
            check="penalty",
            incident="foul",
            decision="penalty" if award else "no_penalty",
            overturned=award,
            on_field_review=True,
            related=start_idx,
            subject=self._pid(defender),
            **self._xy(spot),
        )
        if award:
            self._emit(
                "foul",
                team=int(self.team_of[defender]),
                player=defender,
                fouled=self._pid(attacker),
                foul_type="challenge",
                advantage=False,
                penalty=True,
                card=None,
                **self._xy(spot),
                freeze_frame=None,
            )
            a_team = int(self.team_of[attacker])
            self._set_restart("penalty", a_team, self._penalty_spot(a_team), float(s.rng.uniform(40, 70)))
            return
        self._set_restart(
            "drop_ball", int(self.team_of[defender]), s.pos[self._gk(int(self.team_of[defender]))].copy(), 5.0
        )

    # ------------------------------------------------------------------------------------
    # Crosses and goals
    # ------------------------------------------------------------------------------------

    def _cross(self, c: int, zone_frame: np.ndarray, receiver: int, pass_type: str = "open_play") -> None:
        s = self.s
        team = int(self.team_of[c])
        frame = s.direction[team]
        start = s.pos[c].copy()
        zone = to_frame(zone_frame, frame)
        P = self._frame_pos(team)
        opp_out = self._outfield_idx(1 - team)
        dist = float(np.hypot(*(zone - start)))
        v0 = float(np.clip(17.0 + 0.2 * dist + s.rng.normal(0, 1.5), 14.0, 28.0))
        flight = dist / (0.8 * v0)
        s.last_touch_team = team
        s.carrier = -1
        base = dict(
            height="high",
            pass_type=pass_type,
            body_part="foot",
            cross=True,
            through_ball=False,
            length=round(dist, 2),
            speed_kmh=round(v0 * 3.6, 1),
            **self._xy(start),
        )
        # Everything that decides the cross is known as it's struck: a block by a defender tight to the
        # crosser, the delivery reaching the zone, the keeper coming to claim it, and the aerial duel there.
        d_opp = np.linalg.norm(P[opp_out] - P[c], axis=1)
        p_block = 0.28 if pass_type == "open_play" and float(d_opp.min()) < 2.8 else 0.0
        p_reach = float(np.clip(0.60 + 0.3 * (s.attrs[c]["passing"] - 0.6), 0.35, 0.85))
        gk = self._gk(1 - team)
        claim_zone = zone_frame[0] > LENGTH - 6.5 and abs(zone_frame[1] - HALF_WIDTH) < 9.0
        gk_near = float(np.hypot(*(P[gk] - zone_frame))) < 10.0
        p_claim = (0.30 if claim_zone else 0.08) * (0.6 + 0.8 * s.attrs[gk]["handling"]) * (1.0 if gk_near else 0.5)
        # The aerial duel: the attacker attacking the zone against the nearest defender.
        defender = min(opp_out, key=lambda i: float(np.hypot(*(s.pos[i] - zone))))
        ra, da = s.attrs[receiver], s.attrs[defender]
        p_win = models.aerial_win_prob(ra["heading"], ra["height"], da["heading"], da["height"])
        if pass_type == "corner":
            p_win *= 0.5  # a crowded, set box: defenders win more of these
        # Offside doesn't apply to a corner. Otherwise the receiver is judged as the ball is struck, and
        # commits the offence by going for it.
        offside_applies = pass_type != "corner"
        margin = self._offside_margin(team, receiver, start)
        offside_pos = offside_applies and margin > 0
        recv_spot = s.pos[receiver].copy()
        ff = self._freeze_frame() if offside_pos else None
        truth: dict = dict(
            p_complete=round((1.0 - p_block) * p_reach * (1.0 - p_claim) * p_win, 4),
            regime=s.regimes.current.label,
            offside_margin=round(margin, 3) if offside_applies and float(P[receiver][0]) > LENGTH / 2 else None,
        )
        if p_block and s.rng.random() < p_block:
            blocker = opp_out[int(np.argmin(d_opp))]
            bpos = s.pos[blocker].copy()
            self._emit(
                "pass",
                team=team,
                player=c,
                outcome="incomplete",
                recipient=None,
                under_pressure=True,
                **base,
                **self._end_xy(bpos),
                truth=truth,
            )
            self._advance(0.3, bpos, ("pass", start, bpos, v0, False))
            self._emit("block", team=1 - team, player=blocker, **self._xy(bpos))
            bf = to_frame(bpos, s.direction[1 - team])
            if in_own_box(bf[0], bf[1]) and officials.arm_contact(s.rng, close_range=True):
                self._handball_claim(blocker, c, bpos)
                return
            if s.rng.random() < 0.55:
                self._ball_out(to_frame(np.array([LENGTH, P[c][1] + s.rng.normal(0, 3)]), frame), "goal", 1 - team)
            else:
                self._loose_ball(bpos + s.rng.normal(0, 4, 2), aerial=False, last_team=1 - team)
            return
        if s.rng.random() > p_reach:
            # Overhit or underhit: out of play, or a loose ball for the first defender.
            end = zone + s.rng.normal(0, 7.0, 2)
            out = exit_point(start, end)
            if out is not None:
                self._emit(
                    "pass",
                    team=team,
                    player=c,
                    outcome="out",
                    recipient=None,
                    under_pressure=False,
                    **base,
                    **self._end_xy(out[0]),
                    truth=truth,
                )
                self._advance(flight, out[0], ("pass", start, out[0], v0, True))
                self._ball_out(out[0], out[1], team)
                return
            self._emit(
                "pass",
                team=team,
                player=c,
                outcome="incomplete",
                recipient=None,
                under_pressure=False,
                **base,
                **self._end_xy(end),
                truth=truth,
            )
            self._advance(flight, end, ("pass", start, end, v0, True))
            self._loose_ball(end, aerial=True, cause="clearance")
            return
        if s.rng.random() < p_claim:
            self._emit(
                "pass",
                team=team,
                player=c,
                outcome="incomplete",
                recipient=None,
                under_pressure=False,
                **base,
                **self._end_xy(zone),
                truth=truth,
            )
            self._advance(flight, zone, ("pass", start, zone, v0, True), specials={gk: zone}, urgent={gk}, snap={gk})
            self._emit("goalkeeper", team=1 - team, player=gk, action="claim", outcome="held", **self._xy(zone))
            if not self._raise_delayed_flag():
                self._gain(gk, "claim")
            return
        call = officials.assistant_offside_call(margin, True, s.rng) if offside_pos else None
        if call is not None and call.flag:
            # The flag goes up as the offside attacker goes for the ball.
            idx = self._emit(
                "pass",
                team=team,
                player=c,
                outcome="offside",
                recipient=self._pid(receiver),
                under_pressure=False,
                **base,
                **self._end_xy(zone),
                truth=truth,
                freeze_frame=ff,
            )
            self._advance(flight, zone, ("pass", start, zone, v0, True), specials={receiver: zone}, urgent={receiver})
            self._emit(
                "offside",
                team=team,
                player=receiver,
                pass_event=idx,
                delayed_flag=False,
                **self._xy(recv_spot),
                truth=dict(margin=round(margin, 3)),
            )
            self._set_restart("free_kick", 1 - team, recv_spot, float(s.rng.uniform(20, 35)))
            return
        attacker_wins = s.rng.random() < p_win
        pass_idx = self._emit(
            "pass",
            team=team,
            player=c,
            outcome="complete" if attacker_wins else "incomplete",
            recipient=self._pid(receiver) if attacker_wins else None,
            under_pressure=False,
            **base,
            **self._end_xy(zone),
            truth=truth,
            freeze_frame=ff,
        )
        if call is not None:
            s.offences.append(OffsideOffence(pass_idx, receiver, margin, recv_spot, delayed=call.delayed))
        self._advance(
            flight,
            zone,
            ("pass", start, zone, v0, True),
            specials={receiver: zone, defender: zone},
            urgent={receiver, defender},
            snap={receiver if attacker_wins else defender},
        )
        winner, loser = (receiver, defender) if attacker_wins else (defender, receiver)
        self._emit(
            "duel",
            team=int(self.team_of[winner]),
            player=winner,
            opponent=self._pid(loser),
            duel_type="aerial",
            outcome="won",
            **self._xy(zone),
            truth=dict(p_win=round(p_win if attacker_wins else 1.0 - p_win, 4)),
        )
        if attacker_wins:
            s.last_pass = (pass_idx, c, receiver)
            s.carrier = receiver
            if s.rng.random() < 0.72:
                fz = to_frame(zone, frame)
                cone = decide._defenders_in_cone(fz, P[opp_out])
                xg = models.expected_goal(
                    fz[0],
                    fz[1],
                    True,
                    0.6,
                    cone,
                    False,
                    ra["finishing"],
                    s.attrs[gk]["gk_skill"],
                    edge=self._edge(team),
                )
                self._shot(receiver, None, header=True, xg_override=xg, blockers=cone)
            else:
                self._header_on(receiver, zone)
            return
        if s.rng.random() < 0.2:
            behind = to_frame(
                np.array([LENGTH, HALF_WIDTH + np.sign(zone_frame[1] - HALF_WIDTH + 1e-6) * s.rng.uniform(8, 25)]),
                frame,
            )
            self._emit(
                "clearance", team=1 - team, player=defender, body_part="head", **self._xy(zone), **self._end_xy(behind)
            )
            s.last_touch_team = 1 - team
            self._advance(0.8, behind, ("pass", zone, behind, 14.0, True))
            self._ball_out(behind, "goal", 1 - team)
            return
        if zone_frame[0] > LENGTH - 8.0 and s.rng.random() < 0.016:
            # The defender's header beats their own keeper.
            self._goal(team, defender, pass_idx, deflector=None, shot_type="open_play", own_goal=True, header=True)
            return
        clear_f = np.array([s.rng.uniform(20.0, 38.0), HALF_WIDTH + s.rng.normal(0, 14)])
        clear_abs = to_frame(clear_f, s.direction[1 - team])
        out = exit_point(zone, clear_abs)
        self._emit(
            "clearance",
            team=1 - team,
            player=defender,
            body_part="head",
            **self._xy(zone),
            **self._end_xy(out[0] if out else clear_abs),
        )
        s.last_touch_team = 1 - team
        if out is not None:
            self._advance(1.2, out[0], ("pass", zone, out[0], 16.0, True))
            self._ball_out(out[0], out[1], 1 - team)
            return
        self._advance(1.4, clear_abs, ("pass", zone, clear_abs, 16.0, True))
        self._loose_ball(clear_abs, aerial=True, cause="clearance")

    def _goal(
        self,
        team: int,
        scorer: int,
        shot_idx: int,
        deflector: int | None,
        shot_type: str,
        own_goal: bool = False,
        header: bool | None = None,
    ) -> None:
        """A goal for `team`. For an own goal, `scorer` is the defender who put it in.

        shot_idx is the event the goal came from: the shot, or the cross a defender headed in. header
        says whether the scorer's touch was a header; by default it's read from that event.
        """
        s = self.s
        assist = None
        if not own_goal and s.last_pass is not None and s.last_pass[2] == scorer and shot_type == "open_play":
            assist = self._pid(s.last_pass[1])
        s.score[team] += 1
        s.carrier = -1
        goal_idx = self._emit(
            "goal",
            team=team,
            player=scorer,
            assist=assist,
            own_goal=own_goal,
            score=list(s.score),
            from_event=shot_idx,
            shot_type=shot_type,
            play_pattern=s.play_pattern,
            set_piece=self._set_piece_phase(),
            header=self.events[shot_idx].get("body_part") == "head" if header is None else header,
            truth=dict(
                scorer=self._pid(scorer),
                own_goal=own_goal,
                deflected_by=self._pid(deflector) if deflector is not None else None,
            ),
        )
        celebration = float(np.clip(s.rng.normal(72.0, 12.0), 40.0, 110.0))
        s.time_lost += celebration
        offences = list(s.offences)
        s.offences = []
        kickoff = np.array([LENGTH / 2, HALF_WIDTH])
        foul_in_build_up = not offences and not own_goal and s.rng.random() < officials.APP_FOUL_RATE
        if not offences and not foul_in_build_up:
            self._set_restart("kick_off", 1 - team, kickoff, celebration)
            s.regimes.on_goal(s.period, s.t, self._context(), s.rng)
            return
        # VAR checks the attacking phase: an offside the assistant didn't flag, or a foul missed in
        # the build-up (which the simulation doesn't play out move by move; it's drawn at this point).
        if offences:
            o = offences[0]
            incident, subject, spot = "offside", o.player, o.spot
            truth: dict = dict(margin=round(o.margin, 3))
            extra: dict = dict(pass_event=o.pass_event)
        else:
            attackers = [i for i in self._outfield_idx(team) if self.slots[i].line != "def"]
            subject = int(s.rng.choice(attackers)) if attackers else scorer
            spot_f = np.array([LENGTH - s.rng.uniform(8.0, 22.0), HALF_WIDTH + s.rng.normal(0, 9)])
            spot = to_frame(spot_f, s.direction[team])
            incident = "foul"
            truth = dict(foul_in_build_up=True)
            extra = {}
        start_idx = self._emit(
            "var_check",
            status="started",
            check="goal",
            incident=incident,
            on_field_decision="goal",
            subject=self._pid(subject),
            related=goal_idx,
            **self._xy(spot),
            **extra,
            truth=truth,
        )
        duration = float(np.clip(s.rng.lognormal(np.log(80.0), 0.35), 40.0, 240.0))
        s.time_lost += duration
        ball = s.ball[:2].copy()
        self._stoppage(min(celebration, 40.0), ball, urgency_scale=0.5)
        self._stoppage(duration, ball, urgency_scale=0.3)
        if offences:
            disallowed = officials.var_offside_check(offences[0].margin, s.rng)
        else:
            disallowed = s.rng.random() < 0.8
        if disallowed:
            s.score[team] -= 1
        self._emit(
            "var_check",
            status="complete",
            check="goal",
            incident=incident,
            decision="no_goal" if disallowed else "goal",
            overturned=disallowed,
            on_field_review=bool(disallowed and incident == "foul"),
            related=start_idx,
            goal_event=goal_idx,
            subject=self._pid(subject),
            score=list(s.score),
            **self._xy(spot),
            **extra,
            truth=truth,
        )
        if disallowed:
            self._set_restart("free_kick", 1 - team, spot, float(s.rng.uniform(20, 35)))
        else:
            self._set_restart("kick_off", 1 - team, kickoff, max(celebration - 40.0, 10.0))
        s.regimes.on_goal(s.period, s.t, self._context(), s.rng)

    # ------------------------------------------------------------------------------------
    # Restarts
    # ------------------------------------------------------------------------------------

    def _take_restart(self) -> None:
        s = self.s
        r = s.restart
        assert r is not None
        s.restart = None
        team = r.team
        extra = 0.0
        for t in (0, 1):
            plan = s.sub_plan[t]
            if s.windows_used[t] < len(plan) and self._context()["minute"] >= plan[s.windows_used[t]]:
                if self._make_subs(t):
                    extra += 28.0
        s.time_lost += extra
        dead = r.dead_time + extra
        self._possession_for_restart(team, r.spot)
        s.play_pattern = r.kind
        taker = self._restart_taker(r)
        # The restart waits for the taker to walk or jog to the ball.
        walk = float(np.hypot(*(s.pos[taker] - r.spot))) / (0.55 * float(self._vmax()[taker]))
        dead = max(dead, walk)
        if dead > 0.05:
            self._stoppage(
                dead,
                r.spot,
                targets=self._restart_targets(r, taker),
                specials={taker: r.spot},
                snap={taker},
                urgency_scale=0.6,
            )
        s.pos[taker] = r.spot.copy()
        s.vel[taker] = 0.0
        s.ball[:2] = r.spot
        s.carrier = taker
        s.restart_at = s.t
        s.last_touch_team = team
        it = self._intent(team, True)
        if r.kind == "kick_off":
            self._kick_off(taker)
        elif r.kind == "penalty":
            xg = models.expected_goal(
                0,
                0,
                False,
                0,
                0,
                False,
                s.attrs[taker]["finishing"],
                s.attrs[self._gk(1 - team)]["gk_skill"],
                penalty=True,
            )
            self._shot(taker, None, shot_type="penalty", xg_override=xg, blockers=0)
        elif r.kind == "corner":
            self._corner(taker)
        elif r.kind == "free_kick":
            self._free_kick(taker, it)
        else:
            self._restart_pass(taker, it, r.kind)

    def _possession_for_restart(self, team: int, spot: np.ndarray) -> None:
        s = self.s
        if team != s.poss_team:
            prev = s.poss_team
            s.poss_team = team
            s.possession_seq += 1
            s.offences = []
            s.last_pass = None
            self._emit("possession_change", team=team, from_team=prev, cause="restart", **self._xy(spot))

    def _restart_taker(self, r: Restart) -> int:
        s = self.s
        if r.kind in ("goal_kick", "drop_ball"):
            return self._gk(r.team)
        outfield = self._outfield_idx(r.team)
        if r.kind == "penalty":
            return max(outfield, key=lambda i: s.attrs[i]["finishing"] + 0.3 * s.attrs[i]["composure"])
        if r.kind == "corner":
            wide = [i for i in outfield if s.roles[i] in ("RW", "LW", "AM", "CM", "RB", "LB")]
            return max(wide or outfield, key=lambda i: s.attrs[i]["passing"])
        if r.kind == "kick_off":
            fwd = [i for i in outfield if self.slots[i].line == "att"] or outfield
            return min(fwd, key=lambda i: float(np.hypot(*(s.pos[i] - r.spot))))
        if r.kind == "free_kick" and to_frame(r.spot, s.direction[r.team])[0] > 70.0:
            return max(outfield, key=lambda i: s.attrs[i]["passing"] + s.attrs[i]["long_shots"])
        return min(outfield, key=lambda i: float(np.hypot(*(s.pos[i] - r.spot))))

    def _restart_targets(self, r: Restart, taker: int) -> np.ndarray:
        s = self.s
        targets = self._team_targets(r.spot, r.team)
        attacking_third = to_frame(r.spot, s.direction[r.team])[0] > 68.0
        for team in (0, 1):
            idx = self._team_idx(team)
            frame = s.direction[team]
            slots = self.sheets[team].slots
            active = s.active[idx]
            attacking = team == r.team
            local_taker = int(taker - team * TEAM_SIZE) if attacking else None
            spot_f = to_frame(r.spot, frame)
            if r.kind == "corner":
                heights = np.array([s.attrs[i]["height"] for i in idx])
                tf = setpieces.corner_targets(slots, active, heights, attacking, local_taker, float(spot_f[1]))
            elif r.kind == "penalty":
                tf = setpieces.penalty_targets(slots, active, attacking, local_taker)
            elif r.kind == "kick_off":
                tf = setpieces.kickoff_targets(slots, active, kicking=attacking)
            elif r.kind == "free_kick" and attacking_third:
                tf = setpieces.wall_targets(
                    slots, active, spot_f, attacking, local_taker, to_frame(targets[idx], frame)
                )
            else:
                continue
            targets[idx] = to_frame(tf, frame)
        return targets

    def _kick_off(self, taker: int) -> None:
        s = self.s
        team = int(self.team_of[taker])
        mates = [int(i) for i in self._active_idx(team) if i != taker and self.slots[i].line == "mid"]
        mates = mates or [int(i) for i in self._active_idx(team) if i != taker]
        j = min(mates, key=lambda i: float(np.hypot(*(s.pos[i] - s.pos[taker]))))
        dist = float(np.hypot(*(s.pos[j] - s.pos[taker])))
        opt = decide.Option(
            "pass",
            0.0,
            to_frame(s.pos[j], s.direction[team]),
            receiver=j,
            p_success=0.97,
            detail=dict(
                flight=max(dist / 9.0, 0.5),
                v0=10.0,
                dist=dist,
                lane=0.0,
                interceptor=-1,
                lane_s=0.0,
                recv_press=0.0,
                into_box=False,
            ),
        )
        self._pass(taker, opt, pass_type="kick_off")

    def _restart_pass(self, taker: int, it: Intent, kind: str) -> None:
        s = self.s
        team = int(self.team_of[taker])
        view = self._view(taker, it)
        options = [o for o in decide.evaluate(view, s.rng, allow_shot=False) if o.kind == "pass"]
        if kind == "throw_in":
            long_throw = self.styles[team]["aerial"] > 0.65 and view.pos[taker][0] > 75.0
            options = [o for o in options if o.detail["dist"] <= (34.0 if long_throw else 26.0)]
            for o in options:
                o.p_success = float(np.clip(o.p_success + 0.06, 0.0, 0.98))
        elif kind == "goal_kick":
            style = self.styles[team]
            for o in options:
                if o.detail["dist"] > 35.0:
                    o.utility += 0.010 * style["directness"] + 0.006 * style["aerial"]
                else:
                    o.utility += 0.006 * style["possession"]
        if not options:
            self._clearance(taker, np.array([60.0, HALF_WIDTH]))
            return
        opt = decide.choose(options, s.attrs[taker]["vision"], False, s.rng)
        self._pass(
            taker,
            opt,
            pass_type=kind if kind != "drop_ball" else "open_play",
            body_part="hands" if kind == "throw_in" else "foot",
        )

    def _corner(self, taker: int) -> None:
        s = self.s
        team = int(self.team_of[taker])
        P = self._frame_pos(team)
        if s.rng.random() < 0.13:
            mates = [int(i) for i in self._active_idx(team) if i != taker]
            j = min(mates, key=lambda i: float(np.hypot(*(P[i] - P[taker]))))
            dist = float(np.hypot(*(P[j] - P[taker])))
            opt = decide.Option(
                "pass",
                0.0,
                P[j].copy(),
                receiver=j,
                p_success=0.9,
                detail=dict(
                    flight=max(dist / 10.0, 0.5),
                    v0=12.0,
                    dist=dist,
                    lane=0.1,
                    interceptor=-1,
                    lane_s=0.0,
                    recv_press=0.2,
                    into_box=False,
                ),
            )
            self._pass(taker, opt, pass_type="corner")
            return
        side = np.sign(P[taker][1] - HALF_WIDTH)
        zones = [
            np.array([99.5, HALF_WIDTH + 3.0 * side]),
            np.array([94.5, HALF_WIDTH]),
            np.array([99.0, HALF_WIDTH - 4.5 * side]),
        ]
        zone = zones[int(s.rng.choice(3, p=[0.38, 0.32, 0.30]))]
        mates = [i for i in self._outfield_idx(team) if i != taker]
        receiver = min(mates, key=lambda i: float(np.hypot(*(P[i] - zone))) - 0.05 * s.attrs[i]["height"])
        self._cross(taker, zone, receiver, pass_type="corner")

    def _free_kick(self, taker: int, it: Intent) -> None:
        s = self.s
        team = int(self.team_of[taker])
        P = self._frame_pos(team)
        me = P[taker]
        d = float(dist_to_goal(me[0], me[1]))
        wide = abs(me[1] - HALF_WIDTH) > 16.0
        if d < 30.0 and not wide and s.rng.random() < 0.55:
            a = s.attrs[taker]
            xg = models.expected_goal(
                me[0],
                me[1],
                False,
                0.0,
                3,
                False,
                0.5 * (a["finishing"] + a["long_shots"]),
                s.attrs[self._gk(1 - team)]["gk_skill"],
                direct_free_kick=True,
                edge=self._edge(team),
            )
            self._shot(taker, None, shot_type="free_kick", xg_override=xg, blockers=2)
            return
        if me[0] > 72.0 and (wide or d < 34.0):
            mates = [i for i in self._outfield_idx(team) if i != taker]
            zone = np.array([97.0, HALF_WIDTH + s.rng.normal(0, 3)])
            # A team-mate who is clearly offside holds back rather than attack the delivery.
            o_line = offside_line(P[self._active_idx(1 - team), 0], float(me[0]))
            onside = [i for i in mates if P[i][0] - o_line <= decide.CLEARLY_OFFSIDE] or mates
            receiver = min(onside, key=lambda i: float(np.hypot(*(P[i] - zone))))
            self._cross(taker, zone, receiver, pass_type="free_kick")
            return
        self._restart_pass(taker, it, "free_kick")

    # ------------------------------------------------------------------------------------
    # Substitutions
    # ------------------------------------------------------------------------------------

    def _make_subs(self, team: int, at_half_time: bool = False) -> int:
        """Use one substitution window. Returns how many changes were made."""
        s = self.s
        remaining = min(s.sub_budget[team], MAX_SUBS) - s.subs_made[team]
        if not at_half_time:
            s.windows_used[team] += 1
        if remaining <= 0 or not s.bench[team]:
            return 0
        if at_half_time:
            n = 1
        else:
            windows_left = len(s.sub_plan[team]) - s.windows_used[team]
            n = remaining if windows_left <= 0 else int(s.rng.integers(1, min(3, remaining) + 1))
        # The least durable starters come off. A substitute stays on once he's come on.
        idx = [i for i in self._outfield_idx(team) if s.occupants[i] not in self.protected and s.entered_at[i] == 0.0]
        tiredness = {i: s.attrs[i]["stamina"] + s.rng.normal(0, 0.08) for i in idx}
        made = 0
        for i in sorted(idx, key=lambda i: tiredness[i])[:n]:
            fits = ROLE_FIT[self.slots[i].role]
            candidates = [pid for pid in s.bench[team] if self.players[pid].role in fits]
            if not candidates:
                candidates = [pid for pid in s.bench[team] if self.players[pid].role != "GK"]
            if not candidates:
                continue
            pid_on = min(
                candidates, key=lambda pid: fits.index(self.players[pid].role) if self.players[pid].role in fits else 99
            )
            pid_off = s.occupants[i]
            s.bench[team].remove(pid_on)
            s.occupants[i] = pid_on
            s.attrs[i] = self._attrs_of(pid_on)
            s.entered_at[i] = self.match_seconds()
            s.subs_made[team] += 1
            s.occupancy_version = len(self.occupancy)
            self.occupancy.append(tuple(s.occupants))
            self._emit("substitution", team=team, player_off=pid_off, player_on=pid_on, half_time=at_half_time)
            made += 1
        return made

    # ------------------------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------------------------

    def lineups(self) -> list[dict]:
        return [
            dict(
                club=sheet.club.id,
                formation=sheet.formation,
                starters=[
                    dict(player=p.id, slot=slot.name, position=slot.role)
                    for p, slot in zip(sheet.starters, sheet.slots, strict=True)
                ],
                bench=[p.id for p in sheet.bench],
            )
            for sheet in self.sheets
        ]
