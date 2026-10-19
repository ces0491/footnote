"""Fixtures and match generation.

Every match's seed is derived from the league seed and the match ID, so any
match can be regenerated on its own and a season can be generated in parallel
in any order with the same result.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np

from footnote.generator.feed import CorrectionPlan, MatchInfo, MatchOutput, build_output
from footnote.generator.league import League, Official
from footnote.generator.rng import derive_seed, make_rng
from footnote.generator.sim import MatchSim
from footnote.generator.tracking import Tracking, build_tracking

SEASON_START = datetime(2026, 8, 15, tzinfo=UTC)  # a Saturday
# Kick-off slots across a matchday weekend, as (day offset, hour, minute) in UTC.
SLOTS = [(0, 11, 30)] + [(0, 14, 0)] * 5 + [(0, 16, 30)] + [(1, 13, 0)] * 2 + [(1, 15, 30)]


@dataclass(frozen=True)
class Fixture:
    matchday: int
    home: str
    away: str
    kickoff: datetime

    @property
    def match_id(self) -> str:
        return f"fl-2627-md{self.matchday:02d}-{self.home.lower()}-{self.away.lower()}"


def fixtures(league: League) -> list[Fixture]:
    """A double round robin by the circle method: 38 matchdays of 10 matches, one a week."""
    codes = [c.spec.code for c in league.clubs]
    rng = make_rng(league.seed, "fixtures")
    order = list(rng.permutation(codes))
    n = len(order)
    rounds: list[list[tuple[str, str]]] = []
    teams = order[:]
    for r in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a, b = teams[i], teams[n - 1 - i]
            pairs.append((a, b) if (r + i) % 2 == 0 else (b, a))
        rounds.append(pairs)
        teams = [teams[0]] + [teams[-1]] + teams[1:-1]
    second = [[(b, a) for a, b in pairs] for pairs in rounds]
    out: list[Fixture] = []
    for md, pairs in enumerate(rounds + second, start=1):
        weekend = SEASON_START + timedelta(weeks=md - 1)
        slots = [SLOTS[k] for k in rng.permutation(len(SLOTS))]
        for (home, away), (day, hour, minute) in zip(pairs, slots, strict=True):
            kickoff = weekend + timedelta(days=day, hours=hour, minutes=minute)
            out.append(Fixture(md, str(home), str(away), kickoff))
    return out


def match_seed(league: League, match_id: str) -> int:
    return derive_seed(league.seed, "match", match_id)


def referee_for(league: League, match_id: str) -> Official:
    return league.referees[int(make_rng(match_seed(league, match_id), "referee").integers(len(league.referees)))]


@dataclass
class GeneratedMatch:
    output: MatchOutput
    tracking: Tracking | None
    sim: MatchSim


def generate_match(
    league: League,
    fixture: Fixture,
    reseeds: list[tuple[int, int]] | None = None,
    correction: CorrectionPlan | None = None,
    with_tracking: bool = False,
    match_id: str | None = None,
    protected: set[str] | None = None,
) -> GeneratedMatch:
    mid = match_id or fixture.match_id
    seed = match_seed(league, mid)
    players = {p.id: p for c in league.clubs for p in c.squad}
    referee = referee_for(league, mid)
    home, away = league.club(fixture.home), league.club(fixture.away)
    sim = MatchSim(home, away, mid, seed, referee, players, reseeds=reseeds, protected=protected)
    sim.run()
    info = MatchInfo(
        match_id=mid,
        competition=league.name,
        season=league.season,
        matchday=fixture.matchday,
        kickoff=fixture.kickoff,
        venue=home.spec.ground,
    )
    output = build_output(sim, info, referee, correction)
    return GeneratedMatch(output=output, tracking=build_tracking(sim) if with_tracking else None, sim=sim)


def summarise(gm: GeneratedMatch) -> dict:
    """Match-level statistics used by the calibration report."""
    ev = gm.sim.events
    out: dict = dict(
        match_id=gm.sim.match_id,
        home=gm.sim.clubs[0].id,
        away=gm.sim.clubs[1].id,
        home_goals=gm.sim.s.score[0],
        away_goals=gm.sim.s.score[1],
    )
    for team, side in ((0, "home"), (1, "away")):
        passes = [e for e in ev if e["type"] == "pass" and e.get("team") == team]
        shots = [e for e in ev if e["type"] == "shot" and e.get("team") == team]
        out[f"{side}_passes"] = len(passes)
        out[f"{side}_passes_complete"] = sum(e["outcome"] == "complete" for e in passes)
        out[f"{side}_shots"] = len(shots)
    shots = [e for e in ev if e["type"] == "shot"]
    # A goal VAR rules out stays in the event log, followed by the check that disallowed it.
    disallowed = {e["goal_event"] for e in ev if e["type"] == "var_check" and e.get("decision") == "no_goal"}
    counted = [e for i, e in enumerate(ev) if e["type"] == "goal" and i not in disallowed]
    cards = [e for e in ev if e["type"] == "card"]
    restarts = [e["restart"] for e in ev if e["type"] == "ball_out"]
    out.update(
        shots=len(shots),
        shots_on_target=sum(e["outcome"] in ("goal", "saved") for e in shots),
        shots_blocked=sum(e["outcome"] == "blocked" for e in shots),
        xg=sum(e["truth"]["xg"] for e in shots),
        corners=restarts.count("corner"),
        throw_ins=restarts.count("throw_in"),
        goal_kicks=restarts.count("goal_kick"),
        fouls=sum(e["type"] == "foul" for e in ev),
        offsides=sum(e["type"] == "offside" for e in ev),
        yellow_cards=sum(c["card"] == "yellow" for c in cards),
        red_cards=sum(c["card"] in ("red", "second_yellow") for c in cards),
        penalties=sum(e["type"] == "shot" and e["shot_type"] == "penalty" for e in ev),
        penalty_goals=sum(e["type"] == "shot" and e["shot_type"] == "penalty" and e["outcome"] == "goal" for e in ev),
        own_goals=sum(g["own_goal"] for g in counted),
        headed_goals=sum(bool(g.get("header")) and not g["own_goal"] for g in counted),
        set_piece_goals=sum(bool(g.get("set_piece")) for g in counted if g["shot_type"] != "penalty"),
        goals=len(counted),
        var_overturns=sum(
            e["type"] == "var_check" and e["status"] == "complete" and bool(e.get("overturned")) for e in ev
        ),
        added_minutes=sum(e["minutes"] for e in ev if e["type"] == "added_time"),
        match_seconds=sum(e["t"] for e in ev if e["type"] == "period_end"),
        ball_in_play_seconds=_ball_in_play(gm.sim),
    )
    return out


def _ball_in_play(sim: MatchSim) -> float:
    kf = sim.keyframes
    dead = sum(
        cur.t - prev.t
        for prev, cur in zip(kf, kf[1:], strict=False)
        if cur.period == prev.period and cur.ball_path[0] == "dead"
    )
    total = sum(e["t"] for e in sim.events if e["type"] == "period_end")
    return float(total - dead)


def physical_summary(gm: GeneratedMatch) -> dict:
    """Distance and speed figures from the tracking, per team and per player."""
    tr = gm.tracking
    assert tr is not None
    dt = 1.0 / 10.0
    same = (tr.period[1:] == tr.period[:-1]) & (tr.occupancy[1:] == tr.occupancy[:-1])
    step = np.linalg.norm(np.diff(tr.players, axis=0), axis=2)
    step[~same] = 0.0
    step = np.nan_to_num(step)
    speed = step / dt
    team_distance = [float(step[:, :11].sum()), float(step[:, 11:].sum())]
    high = [float((step * (speed > 5.5))[:, k * 11 : (k + 1) * 11].sum()) for k in (0, 1)]
    sprint = [float((step * (speed > 7.0))[:, k * 11 : (k + 1) * 11].sum()) for k in (0, 1)]
    # Per player: distance and top speed over the whole match, following each slot's occupants.
    per_player: dict[str, dict[str, float]] = {}
    occ = tr.occupancy[1:]
    for version, slots in enumerate(tr.slot_players):
        rows = occ == version
        if not rows.any():
            continue
        for slot, pid in enumerate(slots):
            d = float(step[rows, slot].sum())
            if d == 0.0:
                continue
            # Top speed over a one-second window, as tracking providers report it.
            v = np.convolve(speed[rows, slot], np.ones(10) / 10, mode="valid")
            rec = per_player.setdefault(pid, dict(distance=0.0, top_speed=0.0))
            rec["distance"] += d
            rec["top_speed"] = max(rec["top_speed"], float(v.max()) if len(v) else 0.0)
    return dict(team_distance=team_distance, high_intensity=high, sprint=sprint, players=per_player)
