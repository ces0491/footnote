"""The provider layer: from what happened to what the data feed says happened.

The simulation's raw events carry the truth: true probabilities, offside
margins, arm positions, the true goalscorer. This module splits them in two:

- the feed: messages a live data provider would publish, with stable event IDs,
  club and player IDs, the match clock and a wall-clock timestamp, and nothing
  hidden;
- the answer key: the truth for each event, the hidden regime timeline, team
  strengths and styles, and a record of every provider error.

Like a real provider, the feed is sometimes wrong at first and corrects itself.
A goal that took a deflection can be credited as an own goal and amended a few
minutes later; an assist can be added after review. Each correction is an
`amendment` message carrying the corrected event in full. The match clock stops
at each whistle, so a correction issued at half-time or after the match shows
the clock of the whistle before it; its timestamp says when it was issued.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from footnote.generator.league import Club, Official
from footnote.generator.rng import make_rng
from footnote.generator.sim import PERIOD_SECONDS, MatchSim

FEED_VERSION = "1.0"
HALF_TIME_BREAK = 15 * 60  # seconds between the end of the first half and the second kick-off

# Raw-event fields that hold a pitch index, a team index or an event index, and their feed names.
_PLAYER_FIELDS = {
    "player": "player_id",
    "recipient": "recipient_id",
    "opponent": "opponent_id",
    "fouled": "fouled_id",
    "target": "target_id",
    "goalkeeper": "goalkeeper_id",
    "assist": "assist_id",
    "subject": "subject_id",
    "player_off": "player_off_id",
    "player_on": "player_on_id",
}
_TEAM_FIELDS = {"team": "team_id", "from_team": "from_team_id", "last_touch_team": "last_touch_team_id"}
_EVENT_FIELDS = {
    "pass_event": "pass_event_id",
    "related": "related_event_id",
    "goal_event": "goal_event_id",
    "from_event": "from_event_id",
}

# Chance that a deflected goal is first credited as an own goal, and that the provider then
# corrects it before the final whistle.
OWN_GOAL_MISCALL_RATE = 0.35
IN_MATCH_CORRECTION_RATE = 0.85
ASSIST_REVIEW_RATE = 0.03


@dataclass(frozen=True)
class MatchInfo:
    match_id: str
    competition: str
    season: str
    matchday: int | None
    kickoff: datetime  # UTC
    venue: str


@dataclass(frozen=True)
class ForcedCorrection:
    """Credit this deflected goal (raw event index) as an own goal first, and amend it at (period, t)."""

    event_index: int
    period: int
    t: float


@dataclass(frozen=True)
class CorrectionPlan:
    """Provider behaviour for a match. By default errors and corrections happen at random rates;
    `forced` injects specific ones and `suppress_random` turns the random ones off (the showcase)."""

    forced: tuple[ForcedCorrection, ...] = ()
    suppress_random: bool = False


@dataclass
class MatchOutput:
    meta: dict
    feed: list[dict]
    answer_key: dict


def clock_fields(period: int, t: float) -> dict:
    """Match clock fields for a moment `t` seconds into `period`.

    minute is the minute shown on a broadcast (the 23rd minute runs from 22:00 to 22:59);
    in added time it stays at 45 or 90 and added_minute counts on from 1.
    """
    base = 0 if period == 1 else 45
    if t < PERIOD_SECONDS:
        minute, added = base + int(t // 60) + 1, None
    else:
        minute, added = base + 45, int((t - PERIOD_SECONDS) // 60) + 1
    return dict(
        period=period,
        t=round(t, 2),
        clock=round(t + (0 if period == 1 else PERIOD_SECONDS), 2),
        minute=minute,
        added_minute=added,
    )


@dataclass(frozen=True)
class MatchClock:
    """When each half ended, for placing messages issued while the clock was stopped."""

    first_half_end: float  # seconds into the first half at its final whistle
    match_end: float  # seconds into the second half at the final whistle

    def wall(self, period: int, t: float) -> float:
        """Seconds since kick-off on the wall clock, half-time included."""
        return t if period == 1 else self.first_half_end + HALF_TIME_BREAK + t

    def issued(self, wall: float) -> tuple[int, float, dict]:
        """Where a message issued `wall` seconds after kick-off sorts (period, t) and the clock it shows.

        During half-time t runs on past the first half's whistle, and after the match past the final
        whistle, so the message sorts after that whistle; the clock it shows stays at the whistle.
        """
        if wall <= self.first_half_end:
            return 1, wall, clock_fields(1, wall)
        second_half = self.wall(2, 0.0)
        if wall < second_half:
            return 1, wall, clock_fields(1, self.first_half_end)
        t = wall - second_half
        return 2, t, clock_fields(2, min(t, self.match_end))


def _timestamp(kickoff: datetime, first_half_end: float, period: int, t: float) -> str:
    offset = t if period == 1 else first_half_end + HALF_TIME_BREAK + t
    return (kickoff + timedelta(seconds=offset)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def build_output(
    sim: MatchSim,
    info: MatchInfo,
    referee: Official,
    plan: CorrectionPlan | None = None,
) -> MatchOutput:
    """Turn a finished simulation into feed messages, match metadata and the answer key."""
    plan = plan or CorrectionPlan()
    rng = make_rng(sim.seed, "provider", info.match_id)
    clubs: tuple[Club, Club] = sim.clubs
    team_id = [clubs[0].id, clubs[1].id]
    raw = sim.events
    event_ids = [f"e{i + 1:04d}" for i in range(len(raw))]
    first_half_end = next((e["t"] for e in raw if e["type"] == "period_end" and e["period"] == 1), PERIOD_SECONDS)

    def convert(ev: dict) -> tuple[dict, dict]:
        """Split a raw event into its feed body and its truth."""
        body: dict = {}
        truth = dict(ev.get("truth") or {})
        for k, v in ev.items():
            if k in ("truth", "period", "t"):
                continue
            if k in _PLAYER_FIELDS:
                body[_PLAYER_FIELDS[k]] = v
            elif k in _TEAM_FIELDS:
                body[_TEAM_FIELDS[k]] = team_id[v] if v is not None else None
            elif k in _EVENT_FIELDS:
                body[_EVENT_FIELDS[k]] = event_ids[v] if v is not None else None
            elif k == "score":
                body["score"] = dict(home=v[0], away=v[1])
            elif k == "freeze_frame":
                body["freeze_frame"] = (
                    None
                    if v is None
                    else dict(
                        players=[dict(player_id=p[0], team_id=team_id[p[1]], x=p[2], y=p[3]) for p in v["players"]],
                        ball=dict(x=v["ball"][0], y=v["ball"][1], z=v["ball"][2]),
                    )
                )
            else:
                body[k] = v
        return body, truth

    messages: list[tuple[int, float, int, dict]] = []  # (period, t, order, message) for sorting
    truths: dict[str, dict] = {}
    corrections: list[dict] = []
    order = 0
    match_clock = MatchClock(first_half_end, max((e["t"] for e in raw if e["period"] == 2), default=0.0))
    final_whistle = match_clock.wall(2, match_clock.match_end)

    for i, ev in enumerate(raw):
        body, truth = convert(ev)
        eid = event_ids[i]
        msg = dict(event_id=eid, version=1, **clock_fields(ev["period"], ev["t"]), **body)
        if truth:
            truths[eid] = truth
        if ev["type"] == "goal":
            forced = next((f for f in plan.forced if f.event_index == i), None)
            correction = _goal_credit_call(ev, msg, rng, forced is not None, plan.suppress_random)
            if correction is not None:
                initial, corrected, reason = correction
                msg = initial
                if forced is not None:
                    wall = match_clock.wall(forced.period, forced.t)
                else:
                    wall = match_clock.wall(ev["period"], ev["t"]) + float(rng.uniform(120.0, 360.0))
                    if wall > final_whistle or rng.random() >= IN_MATCH_CORRECTION_RATE:
                        wall = final_whistle + float(rng.uniform(600.0, 3600.0))
                at_period, at_t, shown = match_clock.issued(wall)
                corrections.append(
                    dict(
                        event_id=eid,
                        kind="goal_credit",
                        initial=_credit(initial),
                        corrected=_credit(corrected),
                        reason=reason,
                        issued=dict(period=at_period, t=round(at_t, 2)),
                    )
                )
                order += 1
                messages.append((at_period, at_t, order, _amendment(corrected, initial, reason, shown)))
            elif (
                not plan.suppress_random
                and ev.get("assist") is None
                and not ev.get("own_goal")
                and rng.random() < ASSIST_REVIEW_RATE
            ):
                assister = _likely_assister(i, raw)
                if assister is not None:
                    corrected = dict(msg, version=2, assist_id=assister)
                    wall = match_clock.wall(ev["period"], ev["t"]) + float(rng.uniform(180.0, 600.0))
                    at_period, at_t, shown = match_clock.issued(wall)
                    reason = "assist awarded after review"
                    corrections.append(
                        dict(
                            event_id=eid,
                            kind="assist",
                            initial=None,
                            corrected=assister,
                            reason=reason,
                            issued=dict(period=at_period, t=round(at_t, 2)),
                        )
                    )
                    order += 1
                    messages.append((at_period, at_t, order, _amendment(corrected, msg, reason, shown)))
        order += 1
        messages.append((ev["period"], ev["t"], order, msg))

    meta = _meta(sim, info, referee)
    # The feed opens with the match information, so a consumer needs nothing else to start.
    messages.append(
        (1, -1.0, -1, dict(event_id="e0000", version=1, type="match_info", **clock_fields(1, 0.0), info=meta))
    )
    messages.sort(key=lambda m: (m[0], m[1], m[2]))
    feed: list[dict] = []
    for seq, (period, t, _, msg) in enumerate(messages, start=1):
        out = dict(
            feed_version=FEED_VERSION,
            match_id=info.match_id,
            seq=seq,
            ts=_timestamp(info.kickoff, first_half_end, period, t),
        )
        out.update(msg)
        feed.append(out)

    answer_key = dict(
        match_id=info.match_id,
        seed=sim.seed,
        teams=[dict(club_id=c.id, quality=c.quality, archetype=c.spec.archetype, style=c.style) for c in clubs],
        regimes=sim.s.regimes.timeline(),
        events=truths,
        corrections=corrections,
        players={pid: sim.players[pid].attrs for pid in _involved_players(sim)},
        final_score=dict(home=sim.s.score[0], away=sim.s.score[1]),
    )
    return MatchOutput(meta=meta, feed=feed, answer_key=answer_key)


def _goal_credit_call(
    ev: dict, msg: dict, rng: np.random.Generator, forced: bool, suppress_random: bool
) -> tuple[dict, dict, str] | None:
    """For a deflected goal: maybe credit it first as an own goal. Returns (initial, corrected, reason)."""
    deflector = (ev.get("truth") or {}).get("deflected_by")
    if deflector is None or ev.get("own_goal"):
        return None
    draw = rng.random()  # drawn whatever happens, so forcing one call doesn't shift later draws
    if not forced and (suppress_random or draw >= OWN_GOAL_MISCALL_RATE):
        return None
    initial = dict(msg, player_id=deflector, own_goal=True, assist_id=None)
    corrected = dict(msg, version=2)
    reason = "goal credit reviewed: the shot was on target before the deflection"
    return initial, corrected, reason


def _credit(msg: dict) -> dict:
    return dict(player_id=msg.get("player_id"), own_goal=msg.get("own_goal"), assist_id=msg.get("assist_id"))


def _amendment(corrected: dict, initial: dict, reason: str, shown: dict) -> dict:
    """The amendment message. `shown` is the match clock it carries (see MatchClock.issued)."""
    changes = {
        k: dict(before=initial.get(k), after=corrected.get(k))
        for k in ("player_id", "own_goal", "assist_id")
        if initial.get(k) != corrected.get(k)
    }
    return dict(
        event_id=corrected["event_id"],
        version=corrected["version"],
        type="amendment",
        amends=corrected["type"],
        changes=changes,
        reason=reason,
        corrected_event=dict(corrected),
        **shown,
    )


def _likely_assister(goal_index: int, raw: list[dict]) -> str | None:
    """The last team-mate to pass to the scorer before the goal, if there was one."""
    goal = raw[goal_index]
    scorer, team = goal.get("player"), goal.get("team")
    for ev in reversed(raw[max(0, goal_index - 30) : goal_index]):
        if ev["type"] == "pass" and ev.get("team") == team and ev.get("recipient") == scorer:
            return ev.get("player")
        if ev["type"] == "possession_change":
            break
    return None


def _involved_players(sim: MatchSim) -> list[str]:
    ids = {p.id for sheet in sim.sheets for p in sheet.starters + sheet.bench}
    return sorted(ids)


def _meta(sim: MatchSim, info: MatchInfo, referee: Official) -> dict:
    sheets = sim.sheets
    home, away = sim.clubs
    lineups = []
    for team, sheet in enumerate(sheets):
        lineups.append(
            dict(
                club_id=sheet.club.id,
                formation=sheet.formation,
                starters=[
                    dict(player_id=p.id, slot=slot.name, position=slot.role, shirt=p.shirt, name=p.name)
                    for p, slot in zip(sheet.starters, sheet.slots, strict=True)
                ],
                bench=[dict(player_id=p.id, position=p.role, shirt=p.shirt, name=p.name) for p in sheet.bench],
                # Absolute pitch frame: x runs 0-105 m, y 0-68 m. Home attacks towards x = 105 first.
                attacking_direction=dict(
                    first_half="+x" if team == 0 else "-x", second_half="-x" if team == 0 else "+x"
                ),
            )
        )
    kickoff = info.kickoff.isoformat(timespec="seconds").replace("+00:00", "Z")
    return dict(
        feed_version=FEED_VERSION,
        match_id=info.match_id,
        competition=info.competition,
        season=info.season,
        matchday=info.matchday,
        kickoff=kickoff,
        venue=info.venue,
        referee=dict(id=referee.id, name=referee.name),
        home={k: v for k, v in home.public().items() if k != "squad"},
        away={k: v for k, v in away.public().items() if k != "squad"},
        lineups=lineups,
        pitch=dict(length=105.0, width=68.0, units="m", origin="corner"),
        synthetic=True,
    )
