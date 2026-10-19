"""The showcase match: Saltmarsh Rovers v Kingsferry Athletic.

docs/experience.md tells the story of one match. Rather than scripting it, this
module finds a match the generator produces that tells that story. It runs the
simulation beat by beat; at each beat it snapshots the match and tries reseeded
continuations until the beat happens (the 23rd-minute counter-attack goal, the
goal ruled out for offside, the handball claim VAR turns down). Rare beats are
reached in stages, each retried from a snapshot of the one before: for the 81st
minute, a Kingsferry break, then Adeyani on the ball, then Penhallow in his
shooting lane, then the deflected goal.

Everything in the match is a draw from the same model as every other match; the
search only chooses which draws to keep, so the showcase is a sample conditioned
on the story. The accepted path is saved as a recipe (the step and seed of each
reseed), and `generate_showcase` replays it exactly. Two things are set rather
than searched: the provider layer is told to credit the 81st-minute deflected
goal as an own goal first and amend it at 83:20 on the clock (the 84th minute),
and the named cast are never substituted.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from footnote.generator.decide import cone_mask
from footnote.generator.feed import CorrectionPlan, ForcedCorrection
from footnote.generator.league import League
from footnote.generator.pitch import to_frame
from footnote.generator.rng import derive_seed
from footnote.generator.season import (
    Fixture,
    GeneratedMatch,
    fixtures,
    generate_match,
    match_seed,
    referee_for,
)
from footnote.generator.sim import MatchSim

SHOWCASE_ID = "fl-2627-showcase-sal-kin"
HOME, AWAY = "SAL", "KIN"
VARLAN, DELLOW, PENHALLOW = "sal-10", "sal-09", "sal-04"
ADEYANI, BRENNHOLT = "kin-07", "kin-01"
CAST = (VARLAN, DELLOW, PENHALLOW, ADEYANI, BRENNHOLT)
CORRECTION_AT = (2, 38 * 60 + 20.0)  # 83:20 on the match clock: the 84th minute
MAX_BACKTRACKS = 200


def mt(minute: int, second: float = 0.0) -> tuple[int, float]:
    """Match clock (as shown on screen) to (period, seconds into the period)."""
    if minute < 45:
        return 1, minute * 60 + second
    return 2, (minute - 45) * 60 + second


@dataclass
class Ctx:
    sim: MatchSim
    beat_start_event: int

    @property
    def new_events(self) -> list[dict]:
        return self.sim.events[self.beat_start_event :]

    def regime_share(self, label: str, start: tuple[int, float], end: tuple[int, float]) -> float:
        period = start[0]
        t0, t1 = start[1], end[1]
        total = 0.0
        for seg in self.sim.s.regimes.log:
            if seg.period != period:
                continue
            s_end = seg.end if seg.end is not None else self.sim.s.t
            overlap = max(0.0, min(s_end, t1) - max(seg.start, t0))
            if seg.regime.label == label:
                total += overlap
        return total / max(t1 - t0, 1e-9)


def _goals(events: list[dict]) -> list[dict]:
    return [e for e in events if e["type"] == "goal"]


def _team_frame_u(sim: MatchSim, i: int) -> float:
    team = int(sim.team_of[i])
    return float(to_frame(sim.s.pos[i], sim.s.direction[team])[0])


def _carrier_is(sim: MatchSim, pid: str) -> bool:
    c = sim.s.carrier
    return c >= 0 and sim.s.occupants[c] == pid


@dataclass
class Stage:
    """A step towards a rare beat. The search runs until `reached` turns true within `window`
    seconds of the previous stage, retrying up to `tries` times from a snapshot of that stage."""

    reached: Callable[[Ctx], bool]
    window: float | None = None  # None: any time before the beat ends
    tries: int = 1


@dataclass
class Beat:
    name: str
    end: tuple[int, float]
    accept: Callable[[Ctx], bool]
    goals_allowed: int = 0
    var_checks_allowed: int = 0  # VAR messages (a check starting and completing is two)
    stages: list[Stage] = field(default_factory=list)
    max_tries: int = 400


def _no_red_cards(events: list[dict]) -> bool:
    return not any(e["type"] == "card" and e["card"] in ("red", "second_yellow") for e in events)


def _quiet(ctx: Ctx) -> bool:
    return not _goals(ctx.new_events)


def _shots(sim: MatchSim, team: int, start: tuple[int, float], end: tuple[int, float]) -> int:
    """Shots by a team between two match-clock points."""
    return sum(
        1 for e in sim.events if e["type"] == "shot" and e["team"] == team and start <= (e["period"], e["t"]) < end
    )


def beats() -> list[Beat]:
    """The story in docs/experience.md, as constraints on what the generator produces."""

    def control_early(end_minute: int) -> Callable[[Ctx], bool]:
        def ok(ctx: Ctx) -> bool:
            start = mt(0) if end_minute <= 11 else mt(11)
            first_counter = any(s.regime.label == "transition:away" for s in ctx.sim.s.regimes.log)
            # Saltmarsh's control should show in the shots as well as the possession.
            home, away = _shots(ctx.sim, 0, mt(0), mt(end_minute)), _shots(ctx.sim, 1, mt(0), mt(end_minute))
            shots_ok = away == 0 if end_minute <= 11 else (home >= 3 and away <= 1)
            return (
                not _goals(ctx.new_events)
                and not first_counter
                and shots_ok
                and ctx.regime_share("control:home", start, mt(end_minute)) >= 0.6
            )

        return ok

    def counter_setup(ctx: Ctx) -> bool:
        sim = ctx.sim
        reg = sim.s.regimes.current
        return (
            reg.label == "transition:away"
            and sim.s.carrier >= 0
            and int(sim.team_of[sim.s.carrier]) == 1
            and _team_frame_u(sim, sim.s.carrier) > 55.0
            and mt(21, 40)[1] <= sim.s.t < mt(22, 55)[1]
        )

    def counter_goal(ctx: Ctx) -> bool:
        goals = _goals(ctx.new_events)
        if len(goals) != 1:
            return False
        g = goals[0]
        shot = ctx.sim.events[g["from_event"]]
        return (
            g["team"] == 1
            and not g["own_goal"]
            and g["period"] == 1
            and mt(22)[1] <= g["t"] < mt(23)[1]
            and shot.get("truth", {}).get("regime") == "transition:away"
        )

    def first_counter_ok(ctx: Ctx) -> bool:
        transitions = [s for s in ctx.sim.s.regimes.log if s.regime.label == "transition:away"]
        return counter_goal(ctx) and len(transitions) >= 1 and transitions[0].start >= mt(21, 30)[1]

    def varlan_on_the_ball(ctx: Ctx) -> bool:
        sim = ctx.sim
        return (
            _carrier_is(sim, VARLAN)
            and _team_frame_u(sim, sim.s.carrier) > 55.0
            and mt(29, 45)[1] <= sim.s.t < mt(30, 52)[1]
        )

    def dellow_offside_unflagged(ctx: Ctx) -> bool:
        sim = ctx.sim
        if not (mt(29, 45)[1] <= sim.s.t < mt(30, 58)[1]):
            return False
        for o in sim.s.offences:
            passer = sim.events[o.pass_event].get("player")
            if sim.s.occupants[o.player] == DELLOW and passer == VARLAN:
                return True
        return False

    def offside_goal(ctx: Ctx) -> bool:
        goals = _goals(ctx.new_events)
        return (
            len(goals) == 1
            and goals[0]["player"] == DELLOW
            and goals[0]["period"] == 1
            and mt(30)[1] <= goals[0]["t"] < mt(31)[1]
        )

    def offside_ruled_out(ctx: Ctx) -> bool:
        if not offside_goal(ctx):
            return False
        checks = [e for e in ctx.new_events if e["type"] == "var_check" and e["status"] == "complete"]
        return any(
            c["incident"] == "offside" and c["decision"] == "no_goal" and c.get("subject") == DELLOW for c in checks
        )

    def pressure_before_half(ctx: Ctx) -> bool:
        return (
            not _goals(ctx.new_events)
            and ctx.regime_share("pressure:home", mt(38), mt(44, 59)) >= 0.5
            and _shots(ctx.sim, 0, mt(38), (2, 0.0)) >= 3
        )

    def equaliser_setup(ctx: Ctx) -> bool:
        sim = ctx.sim
        return (
            sim.s.period == 2
            and sim.s.regimes.current.label in ("control:home", "pressure:home")
            and _carrier_is(sim, VARLAN)
            and _team_frame_u(sim, sim.s.carrier) > 72.0
            and mt(50, 45)[1] <= sim.s.t < mt(51, 57)[1]
        )

    def equaliser(ctx: Ctx) -> bool:
        goals = _goals(ctx.new_events)
        if len(goals) != 1:
            return False
        g = goals[0]
        shot = ctx.sim.events[g["from_event"]]
        return (
            g["player"] == VARLAN
            and g["period"] == 2
            and mt(51)[1] <= g["t"] < mt(52)[1]
            and shot["type"] == "shot"
            and shot["distance"] >= 20.0
            and shot.get("truth", {}).get("regime") in ("control:home", "pressure:home")
        )

    def chaos_spell(ctx: Ctx) -> bool:
        return not _goals(ctx.new_events) and ctx.regime_share("chaos", mt(63), mt(68)) >= 0.6

    def handball_setup(ctx: Ctx) -> bool:
        sim = ctx.sim
        return (
            sim.s.period == 2
            and sim.s.carrier >= 0
            and int(sim.team_of[sim.s.carrier]) == 0
            and _team_frame_u(sim, sim.s.carrier) > 76.0
            and mt(72, 50)[1] <= sim.s.t < mt(73, 55)[1]
        )

    def handball_check_started(ctx: Ctx) -> bool:
        return any(
            e["type"] == "var_check"
            and e["status"] == "started"
            and e["incident"] == "handball"
            and e.get("on_field_decision") == "no_penalty"
            and mt(73)[1] <= e["t"] < mt(74)[1]
            and e["period"] == 2
            for e in ctx.new_events
        )

    def handball_no_penalty(ctx: Ctx) -> bool:
        done = [
            e
            for e in ctx.new_events
            if e["type"] == "var_check" and e["status"] == "complete" and e["incident"] == "handball"
        ]
        return (
            handball_check_started(ctx)
            and len(done) == 1
            and done[0]["decision"] == "no_penalty"
            and not _goals(ctx.new_events)
        )

    def kingsferry_break(ctx: Ctx) -> bool:
        sim = ctx.sim
        return (
            sim.s.period == 2
            and sim.s.regimes.current.label == "transition:away"
            and mt(79, 25)[1] <= sim.s.t < mt(80, 45)[1]
        )

    def penhallow_in_the_way(sim: MatchSim) -> bool:
        """Penhallow stands in Adeyani's shooting lane, close enough to get a touch on a shot."""
        if PENHALLOW not in sim.s.occupants:
            return False
        frame = to_frame(sim.s.pos, sim.s.direction[1])
        me = frame[sim.s.carrier]
        pen = frame[sim.s.occupants.index(PENHALLOW)]
        return bool(cone_mask(me, pen[None, :], reach=2.0)[0]) and float(np.hypot(*(pen - me))) < 18.0

    def winner_setup(ctx: Ctx) -> bool:
        sim = ctx.sim
        return (
            sim.s.period == 2
            and sim.s.regimes.current.label == "transition:away"
            and _carrier_is(sim, ADEYANI)
            and _team_frame_u(sim, sim.s.carrier) > 62.0
            and mt(79, 40)[1] <= sim.s.t < mt(80, 57)[1]
        )

    def adeyani_lines_up(ctx: Ctx) -> bool:
        sim = ctx.sim
        return (
            _carrier_is(sim, ADEYANI)
            and sim.s.regimes.current.label == "transition:away"
            and penhallow_in_the_way(sim)
            and sim.s.t < mt(80, 58)[1]
        )

    def winner(ctx: Ctx) -> bool:
        goals = _goals(ctx.new_events)
        if len(goals) != 1:
            return False
        g = goals[0]
        truth = g.get("truth", {})
        return (
            g["player"] == ADEYANI
            and not g["own_goal"]
            and truth.get("deflected_by") == PENHALLOW
            and g["period"] == 2
            and mt(80)[1] <= g["t"] < mt(81)[1]
        )

    def winner_stands(ctx: Ctx) -> bool:
        return winner(ctx) and not any(
            e["type"] == "var_check" and e.get("decision") == "no_goal" for e in ctx.new_events
        )

    return [
        Beat("control_0_11", mt(11), control_early(11), max_tries=300),
        Beat("control_11_21", mt(21), control_early(21), max_tries=300),
        Beat(
            "first_counter_goal_23",
            mt(24),
            first_counter_ok,
            goals_allowed=1,
            stages=[Stage(counter_setup), Stage(counter_goal, window=25.0, tries=600)],
        ),
        Beat("quiet_24_29", mt(29, 40), _quiet),
        Beat(
            "offside_goal_31",
            mt(34, 30),
            offside_ruled_out,
            goals_allowed=1,
            stages=[
                Stage(varlan_on_the_ball),
                Stage(dellow_offside_unflagged, window=8.0, tries=800),
                Stage(offside_goal, window=20.0, tries=300),
            ],
            var_checks_allowed=2,
        ),
        Beat("quiet_34_36", mt(36), _quiet),
        Beat("pressure_38_45", (2, 0.0), pressure_before_half, max_tries=400),
        Beat("quiet_46_49", mt(49, 30), _quiet),
        Beat(
            "equaliser_52",
            mt(53, 30),
            equaliser,
            goals_allowed=1,
            stages=[Stage(equaliser_setup), Stage(equaliser, window=12.0, tries=1500)],
            max_tries=150,
        ),
        Beat("quiet_53_63", mt(63), _quiet),
        Beat("chaos_63_68", mt(68), chaos_spell, max_tries=500),
        Beat("quiet_68_73", mt(73, 30), _quiet),
        Beat(
            "handball_claim_74",
            mt(78, 30),
            handball_no_penalty,
            stages=[Stage(handball_setup), Stage(handball_check_started, window=25.0, tries=1500)],
            var_checks_allowed=2,
            max_tries=200,
        ),
        Beat("quiet_78_79", mt(79, 15), _quiet),
        Beat(
            "winner_81",
            mt(82, 30),
            winner_stands,
            goals_allowed=1,
            stages=[
                Stage(kingsferry_break),
                Stage(winner_setup, window=25.0, tries=300),
                Stage(adeyani_lines_up, window=8.0, tries=300),
                Stage(winner, window=12.0, tries=3000),
            ],
            max_tries=300,
        ),
        Beat("to_full_time", (3, 0.0), _quiet),
    ]


@dataclass
class SearchLog:
    beats: list[dict] = field(default_factory=list)


def _violation(ctx: Ctx, beat: Beat) -> bool:
    events = ctx.new_events
    if not _no_red_cards(events):
        return True
    if sum(e["type"] == "var_check" for e in events) > beat.var_checks_allowed:
        return True
    return len(_goals(events)) > beat.goals_allowed


def _run_to(
    sim: MatchSim, ctx: Ctx, beat: Beat, end: tuple[int, float], stop: Callable[[Ctx], bool] | None = None
) -> bool:
    """Step until `end` (or `stop` turns true). False on a violation."""
    while not sim.s.finished and (sim.s.period, sim.s.t) < end:
        sim.step()
        if _violation(ctx, beat):
            return False
        if stop is not None and stop(ctx):
            return True
    return stop is None


def _try_beat(sim: MatchSim, beat: Beat, root: int, attempt: int, log: dict) -> list[tuple[int, int]] | None:
    """One attempt at a beat from the current state. Returns the extra reseeds it needed, or None."""
    ctx = Ctx(sim, len(sim.events))
    return _stages(sim, ctx, beat, 0, (root, beat.name, attempt), log)


def _stages(sim: MatchSim, ctx: Ctx, beat: Beat, k: int, path: tuple, log: dict) -> list[tuple[int, int]] | None:
    if k == len(beat.stages):
        if not _run_to(sim, ctx, beat, beat.end):
            return None
        return [] if beat.accept(ctx) else None
    stage = beat.stages[k]
    snap = sim.snapshot()
    here = (sim.s.period, sim.s.t)
    end = beat.end if stage.window is None else min(beat.end, (here[0], here[1] + stage.window))
    for j in range(stage.tries):
        reseeds: list[tuple[int, int]] = []
        if k > 0:
            # The first stage runs on the beat's own seed; later stages retry from their snapshot.
            sim.restore(snap)
            seed = derive_seed(*path, "stage", k, j)
            sim.reseed(seed)
            reseeds.append((snap.state.steps + 1, seed))
            log[f"stage_{k}_tries"] = log.get(f"stage_{k}_tries", 0) + 1
        if not _run_to(sim, ctx, beat, end, stop=stage.reached):
            continue
        rest = _stages(sim, ctx, beat, k + 1, (*path, "stage", k, j), log)
        if rest is not None:
            return reseeds + rest
    return None


def search(league: League, root: int = 1, verbose: bool = True) -> dict:
    """Find a match that tells the showcase story. Returns the recipe."""
    fx = showcase_fixture(league)
    gm_seed = match_seed(league, SHOWCASE_ID)
    players = {p.id: p for c in league.clubs for p in c.squad}
    referee = referee_for(league, SHOWCASE_ID)
    sim = MatchSim(league.club(HOME), league.club(AWAY), SHOWCASE_ID, gm_seed, referee, players, protected=set(CAST))
    beat_list = beats()
    # One frame per beat on the current path: the snapshot it starts from, the next attempt to try,
    # how many reseeds precede it, and its log entry. If a beat can't be met from its starting state,
    # the search backs up and takes a different continuation of the beat before.
    frames: list[dict] = []
    reseeds: list[tuple[int, int]] = []
    backtracks = 0
    t0 = time.time()
    k = 0
    while k < len(beat_list):
        beat = beat_list[k]
        if len(frames) == k:
            frames.append(
                dict(snap=sim.snapshot(), attempt=0, n_reseeds=len(reseeds), entry=dict(name=beat.name, tries=0))
            )
        frame = frames[k]
        entry = frame["entry"]
        extra = None
        while frame["attempt"] < beat.max_tries:
            attempt = frame["attempt"]
            frame["attempt"] += 1
            sim.restore(frame["snap"])
            seed = derive_seed(root, beat.name, attempt)
            sim.reseed(seed)
            entry["tries"] += 1
            extra = _try_beat(sim, beat, root, attempt, entry)
            if extra is not None:
                del reseeds[frame["n_reseeds"] :]
                reseeds.append((frame["snap"].state.steps + 1, seed))
                reseeds.extend(extra)
                break
        if extra is not None:
            entry["seconds"] = round(time.time() - t0, 1)
            if verbose:
                stages = "  ".join(f"{key}={v}" for key, v in entry.items() if key.startswith("stage_"))
                print(
                    f"  {beat.name:24s} tries {entry['tries']:4d}  {stages}  ({entry['seconds']} s)  "
                    f"score {sim.s.score}"
                )
            k += 1
            continue
        frames.pop()
        backtracks += 1
        if k == 0 or backtracks > MAX_BACKTRACKS:
            raise RuntimeError(f"showcase search failed at beat {beat.name} after {backtracks} backtracks")
        k -= 1
        if verbose:
            print(f"  {beat.name} can't be met from here; trying another {beat_list[k].name}")
    log = SearchLog(beats=[f["entry"] for f in frames])
    # The 81st-minute goal is the one off Penhallow; Adeyani may have scored earlier too.
    winner_goal = next(
        i
        for i, e in enumerate(sim.events)
        if e["type"] == "goal" and e["player"] == ADEYANI and (e.get("truth") or {}).get("deflected_by") == PENHALLOW
    )
    return dict(
        match_id=SHOWCASE_ID,
        league_seed=league.seed,
        home=HOME,
        away=AWAY,
        matchday=fx.matchday,
        kickoff=fx.kickoff.isoformat(),
        root=root,
        reseeds=[list(r) for r in _last_per_step(reseeds)],
        protected=list(CAST),
        corrections=[dict(event_index=winner_goal, period=CORRECTION_AT[0], t=CORRECTION_AT[1])],
        beats=log.beats,
        code_fingerprint=code_fingerprint(),
    )


def _last_per_step(reseeds: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Drop reseeds that a later one at the same step replaced before it took effect.

    That happens when a beat's last step carries the clock past the next beat's end (a long
    stoppage), so the next beat takes no steps and its successor reseeds at the same step.
    """
    out: list[tuple[int, int]] = []
    for step, seed in reseeds:
        if out and out[-1][0] == step:
            out[-1] = (step, seed)
        else:
            out.append((step, seed))
    return out


def showcase_fixture(league: League) -> Fixture:
    """The season's Saltmarsh v Kingsferry fixture supplies the date and kick-off time."""
    return next(f for f in fixtures(league) if f.home == HOME and f.away == AWAY)


def generate_showcase(league: League, recipe: dict, with_tracking: bool = True) -> GeneratedMatch:
    if recipe["league_seed"] != league.seed:
        raise ValueError("recipe was made for a different league seed")
    fx = showcase_fixture(league)
    plan = CorrectionPlan(
        forced=tuple(ForcedCorrection(c["event_index"], c["period"], c["t"]) for c in recipe["corrections"]),
        suppress_random=True,
    )
    reseeds = [(int(step), int(seed)) for step, seed in recipe["reseeds"]]
    return generate_match(
        league,
        fx,
        reseeds=reseeds,
        correction=plan,
        with_tracking=with_tracking,
        match_id=recipe["match_id"],
        protected=set(recipe["protected"]),
    )


def check_story(gm: GeneratedMatch) -> list[str]:
    """The story's facts, checked on a finished match. Returns what fails; empty means it holds."""
    sim = gm.sim
    ev = sim.events
    problems: list[str] = []
    ctx = Ctx(sim, 0)

    def minute(e: dict) -> int:
        return int(e["t"] // 60) + (1 if e["period"] == 1 else 46)

    goals = [e for e in ev if e["type"] == "goal"]
    got = [(minute(g), g["player"]) for g in goals]
    want_minutes = [23, 31, 52, 81]
    if [m for m, _ in got] != want_minutes:
        problems.append(f"goals in minutes {[m for m, _ in got]}, expected {want_minutes}")
    else:
        first, offside, equaliser, winner = goals
        if first["team"] != 1 or ev[first["from_event"]].get("truth", {}).get("regime") != "transition:away":
            problems.append("23': not a Kingsferry goal from a counter-attack")
        transitions = [s for s in sim.s.regimes.log if s.regime.label == "transition:away"]
        if not transitions or transitions[0].start < mt(21)[1] or transitions[0].period != 1:
            problems.append("23': not Kingsferry's first counter-attack")
        ruled_out = [
            e
            for e in ev
            if e["type"] == "var_check" and e["status"] == "complete" and e.get("goal_event") == ev.index(offside)
        ]
        if offside["player"] != DELLOW or not ruled_out or ruled_out[0]["decision"] != "no_goal":
            problems.append("31': Dellow's goal was not ruled out by VAR")
        elif ev[ruled_out[0]["pass_event"]].get("player") != VARLAN:
            problems.append("31': the offside pass was not Varlan's")
        shot = ev[equaliser["from_event"]]
        if equaliser["player"] != VARLAN or shot.get("distance", 0) < 20.0:
            problems.append("52': not Varlan from distance")
        if winner["player"] != ADEYANI or winner.get("truth", {}).get("deflected_by") != PENHALLOW:
            problems.append("81': not Adeyani's shot deflected off Penhallow")
    if sim.s.score != [1, 2]:
        problems.append(f"final score {sim.s.score}, expected [1, 2]")
    if ctx.regime_share("control:home", mt(0), mt(21)) < 0.6:
        problems.append("0-21': Saltmarsh not in control")
    if ctx.regime_share("pressure:home", mt(38), mt(44, 59)) < 0.5 or _shots(sim, 0, mt(38), (2, 0.0)) < 3:
        problems.append("38-45': no sustained Saltmarsh pressure")
    if _shots(sim, 0, mt(0), mt(21)) < 3 or _shots(sim, 1, mt(0), mt(21)) > 1:
        problems.append("0-21': Saltmarsh's control doesn't show in the shots")
    checks = [e for e in ev if e["type"] == "var_check"]
    if sorted({minute(e) for e in checks if e["status"] == "started"}) != [31, 74]:
        problems.append(
            f"VAR checks start in minutes {sorted({minute(e) for e in checks if e['status'] == 'started'})}"
        )
    if ctx.regime_share("chaos", mt(63), mt(68)) < 0.6:
        problems.append("63-68': no chaos")
    started = [
        e
        for e in ev
        if e["type"] == "var_check"
        and e["status"] == "started"
        and e["incident"] == "handball"
        and e["period"] == 2
        and minute(e) == 74
        and e.get("on_field_decision") == "no_penalty"
    ]
    turned_down = [
        e
        for e in ev
        if e["type"] == "var_check"
        and e["status"] == "complete"
        and e.get("related") in {ev.index(s) for s in started}
        and e["decision"] == "no_penalty"
    ]
    if not turned_down:
        problems.append("74': no handball claim turned down by VAR")
    if not _no_red_cards(ev):
        problems.append("a red card")
    amendments = [m for m in gm.output.feed if m["type"] == "amendment"]
    if (
        len(amendments) != 1
        or amendments[0]["minute"] != 84
        or amendments[0]["changes"].get("player_id", {}).get("after") != ADEYANI
    ):
        problems.append("expected one amendment in the 84th minute crediting Adeyani")
    return problems


# The modules whose code decides what a match contains. A recipe replays only on the code that found it.
GENERATING_MODULES = (
    "decide",
    "feed",
    "formations",
    "league",
    "models",
    "movement",
    "names",
    "officials",
    "pitch",
    "regimes",
    "rng",
    "season",
    "setpieces",
    "sim",
    "tracking",
)


def code_fingerprint() -> str:
    """Hash of the source of the modules that generate a match."""
    root = Path(__file__).parent
    h = hashlib.sha256()
    for name in GENERATING_MODULES:
        h.update(name.encode())
        # Line endings are normalised (CRLF to LF) so Windows and Linux checkouts agree.
        data = (root / f"{name}.py").read_bytes()
        h.update(data.replace(bytes((13, 10)), bytes((10,))))
    return h.hexdigest()[:16]


def save_recipe(recipe: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(recipe, indent=1) + "\n", encoding="utf-8", newline="\n")


def load_recipe(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = ["CAST", "SHOWCASE_ID", "beats", "check_story", "generate_showcase", "search"]
