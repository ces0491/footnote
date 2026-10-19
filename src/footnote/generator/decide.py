"""What the player on the ball chooses to do.

Every option is scored in the same currency, the chance of a goal: the threat of
where the ball ends up times the chance of getting it there, less the threat
handed to the opponent if it goes wrong. The team's intent (style plus regime)
weights progress against safety; a softmax with player-dependent noise picks
the action, so better decision-makers pick the best option more often.

All geometry here is in the acting team's frame.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from footnote.generator import models
from footnote.generator.movement import offside_line
from footnote.generator.pitch import HALF_WIDTH, LENGTH, WIDTH, dist_to_goal, in_attacking_box
from footnote.generator.regimes import Intent


@dataclass
class Option:
    kind: str  # "pass", "shot", "carry", "cross", "clear"
    utility: float
    target: np.ndarray
    receiver: int = -1
    lofted: bool = False
    through: bool = False
    p_success: float = 1.0
    detail: dict = field(default_factory=dict)


@dataclass
class View:
    """The pitch as the player on the ball sees it, in their team's frame."""

    carrier: int
    pos: np.ndarray  # (22, 2) all players, team frame
    vel: np.ndarray  # (22, 2) velocities, team frame
    mates: np.ndarray  # pitch indices of active team-mates, carrier excluded
    opps: np.ndarray  # pitch indices of active opponents
    opp_speed: np.ndarray  # (len(opps),) usable speed of each opponent
    roles: list[str]  # role of each pitch index
    attrs: list[dict[str, float]]  # attributes of each pitch index
    gk_skill: float  # opposing goalkeeper
    intent: Intent
    style: dict[str, float]
    edge: float = 0.0  # the acting team's strength advantage: quality gap plus home edge
    # 0-1: how long the team has been circulating in the final third without a shot. Patience runs
    # out, so the value of simply keeping the ball fades and the appetite for a shot grows.
    impatience: float = 0.0


THROUGH_ROLES = {"ST", "RW", "LW", "AM", "RB", "LB", "CM"}
# Metres beyond the offside line at which a team-mate is plainly offside to the player on the ball.
CLEARLY_OFFSIDE = 1.5


def evaluate(view: View, rng: np.random.Generator, allow_shot: bool = True) -> list[Option]:
    me = view.pos[view.carrier]
    a = view.attrs[view.carrier]
    it = view.intent
    opp_pos = view.pos[view.opps]
    outfield = np.array([view.roles[i] != "GK" for i in view.opps], dtype=bool)
    p_press = models.passer_pressure(me, opp_pos)
    options = _passes(view, me, a, it, opp_pos, p_press)

    # ----- shot -----
    d_goal = float(dist_to_goal(me[0], me[1]))
    if allow_shot and d_goal < 34.0 and me[0] > LENGTH / 2:
        out_pos = opp_pos[outfield]
        cone = int(cone_mask(me, out_pos).sum())
        tight = bool(len(out_pos)) and float(np.linalg.norm(out_pos - me, axis=1).min()) < 3.5
        one_on_one = cone == 0 and not tight and d_goal < 16.0
        xg = models.expected_goal(
            me[0], me[1], False, p_press, cone, one_on_one, a["finishing"], view.gk_skill, edge=view.edge
        )
        skill = a["long_shots"] if d_goal > 20.0 else a["finishing"]
        appetite = it.shoot * (0.45 + 0.45 * skill) * (1.0 + 0.5 * view.impatience)
        u = appetite * xg - (1 - xg) * 0.0025
        options.append(
            Option(
                "shot",
                u,
                np.array([LENGTH, HALF_WIDTH]),
                p_success=xg,
                detail=dict(xg=xg, blockers=cone, one_on_one=one_on_one, dist=d_goal),
            )
        )

    # ----- carry -----
    retention_bonus = (0.011 + 0.004 * view.style["possession"]) * (1.0 - 0.7 * view.impatience)
    cost_here = float(models.turnover_cost(me[0], me[1]))
    max_len = min(4.0 + 9.0 * it.carry * a["dribbling"], 16.0)
    for angle, length in zip((0.0, 0.45, -0.45), _free_run(me, opp_pos, view.opp_speed, max_len), strict=True):
        if length < 3.0:
            continue
        direction = np.array([np.cos(angle), np.sin(angle)])
        target = me + direction * length
        if not (0.5 < target[0] < LENGTH - 0.5 and 0.5 < target[1] < WIDTH - 0.5):
            continue
        crowd = int(np.sum(np.linalg.norm(opp_pos - target, axis=1) < 4.5))
        p_keep = float(models.sigmoid(2.0 + 2.2 * (a["dribbling"] - 0.5) - 1.6 * p_press - 0.55 * crowd))
        value = float(models.threat(target[0], target[1]))
        u = it.carry * p_keep * (value + retention_bonus) - (1 - p_keep) * it.caution * cost_here
        options.append(Option("carry", u, target, p_success=p_keep, detail=dict(length=length, crowd=crowd)))

    # ----- cross -----
    if me[0] > 76.0 and abs(me[1] - HALF_WIDTH) > 15.0:
        side = np.sign(me[1] - HALF_WIDTH)
        o_line = offside_line(opp_pos[:, 0], float(me[0]))
        for zone in ((99.0, HALF_WIDTH + side * 3.5), (94.0, HALF_WIDTH), (98.5, HALF_WIDTH - side * 5.0)):
            z = np.array(zone)
            # A team-mate who is clearly offside holds back rather than attack the cross.
            attackers = [
                int(j)
                for j in view.mates
                if np.hypot(*(view.pos[j] - z)) < 14.0 and view.pos[j][0] - o_line <= CLEARLY_OFFSIDE
            ]
            if not attackers:
                continue
            best = attackers[int(np.argmin([np.hypot(*(view.pos[j] - z)) for j in attackers]))]
            defender = view.opps[int(np.argmin(np.linalg.norm(opp_pos - z, axis=1)))]
            p_win = models.aerial_win_prob(
                view.attrs[best]["heading"],
                view.attrs[best]["height"],
                view.attrs[defender]["heading"],
                view.attrs[defender]["height"],
            )
            p_reach = 0.62 + 0.25 * (a["passing"] - 0.6)
            xg_header = models.expected_goal(
                z[0], z[1], True, 0.5, 1, False, view.attrs[best]["finishing"], view.gk_skill
            )
            u = it.cross * p_reach * p_win * (xg_header + 0.02) - (1 - p_reach * p_win) * 0.003
            options.append(
                Option(
                    "cross",
                    u,
                    z,
                    receiver=int(best),
                    lofted=True,
                    p_success=p_reach * p_win,
                    detail=dict(p_reach=p_reach, p_win=p_win, defender=int(defender)),
                )
            )

    # ----- clearance -----
    if me[0] < 35.0 and (p_press > 0.2 or it.long_ball > 1.2):
        if rng.random() < 0.55:
            # Into touch, or just beyond it.
            landing_v = -2.0 if me[1] < HALF_WIDTH else WIDTH + 2.0
        else:
            landing_v = float(np.clip(me[1] + rng.normal(0, 14), 4.0, WIDTH - 4.0))
        landing = np.array([min(me[0] + rng.uniform(30.0, 55.0), 85.0), landing_v])
        in_box = me[0] < 16.5 and abs(me[1] - HALF_WIDTH) < 20.16
        u = (
            -0.45 * float(models.turnover_cost(landing[0], np.clip(landing[1], 0.0, WIDTH)))
            - 0.001
            + 0.003 * it.long_ball
            + (0.005 * p_press if in_box else 0.0)
        )
        options.append(Option("clear", u, landing, lofted=True))

    return options


def _passes(
    view: View, me: np.ndarray, a: dict[str, float], it: Intent, opp_pos: np.ndarray, p_press: float
) -> list[Option]:
    """Every pass to feet and into space, evaluated together."""
    mates = np.asarray(view.mates, dtype=int)
    if len(mates) == 0:
        return []
    mate_pos = view.pos[mates]
    ends = [mate_pos + view.vel[mates] * 0.5]
    receivers = [mates]
    through = [np.zeros(len(mates), dtype=bool)]
    ahead = mate_pos[:, 0] - me[0]
    runners = np.array([view.roles[j] in THROUGH_ROLES for j in mates]) & (ahead > 2.0) & (mate_pos[:, 0] > 45.0)
    if runners.any():
        run = np.minimum(6.0 + 8.0 * it.risk, np.maximum(0.0, LENGTH - 6.0 - mate_pos[runners, 0]))
        lateral = 0.18 * np.sign(HALF_WIDTH - mate_pos[runners, 1])
        norm = np.hypot(1.0, lateral)
        d = np.stack([1.0 / norm, lateral / norm], axis=1)
        ok = run > 3.0
        ends.append((mate_pos[runners] + d * run[:, None])[ok])
        receivers.append(mates[runners][ok])
        through.append(np.ones(int(ok.sum()), dtype=bool))
    R = np.vstack(ends)
    J = np.concatenate(receivers)
    TH = np.concatenate(through)
    R[:, 0] = np.clip(R[:, 0], 0.5, LENGTH - 0.5)
    R[:, 1] = np.clip(R[:, 1], 0.5, WIDTH - 0.5)
    dist = np.linalg.norm(R - me, axis=1)
    keep = dist >= 3.0
    R, J, TH, dist = R[keep], J[keep], TH[keep], dist[keep]
    if len(R) == 0:
        return []

    ground_v = 0.8 * (7.0 + 0.33 * dist)
    ground_risk, _, _ = models.lane_risk(me, R, opp_pos, view.opp_speed, ground_v, np.zeros(len(R), dtype=bool))
    lofted = (dist > 34.0) | ((dist > 16.0) & (ground_risk > 0.45))
    v0 = np.where(lofted, 13.0 + 0.22 * dist, 7.0 + 0.33 * dist)
    flight = dist / (np.where(lofted, 0.78, 0.80) * v0)
    lane, interceptor, lane_s = models.lane_risk(me, R, opp_pos, view.opp_speed, dist / flight, lofted)
    rp = models.receiver_pressure(R, opp_pos, view.opp_speed, flight)
    into_box = in_attacking_box(R[:, 0], R[:, 1]) & (not bool(in_attacking_box(me[0], me[1])))
    first_touch = np.array([view.attrs[j]["first_touch"] for j in J])
    p = models.pass_completion(
        dist, lofted, lane, rp, p_press, a["passing"], first_touch, it.retention, into_box, edge=view.edge
    )
    p = np.where(TH, p * 0.92, p)

    retention_bonus = (0.011 + 0.004 * view.style["possession"]) * (1.0 - 0.7 * view.impatience)
    value = models.threat(R[:, 0], R[:, 1])
    fail = me + 0.55 * (R - me)
    cost = models.turnover_cost(fail[:, 0], fail[:, 1])
    progress = np.maximum(R[:, 0] - me[0], 0.0)
    o_line = offside_line(opp_pos[:, 0], float(me[0]))
    recv_u = view.pos[J, 0]
    # Passers can see a team-mate who is clearly offside and mostly avoid him.
    clearly_offside = (recv_u - o_line > CLEARLY_OFFSIDE) & (recv_u > me[0])
    u = p * (value + retention_bonus + 0.00035 * it.risk * progress) - (1 - p) * it.caution * cost
    u = u + np.where(lofted & (progress > 25.0), 0.004 * it.long_ball, 0.0) - np.where(clearly_offside, 0.02, 0.0)

    return [
        Option(
            "pass",
            float(u[k]),
            R[k].copy(),
            receiver=int(J[k]),
            lofted=bool(lofted[k]),
            through=bool(TH[k]),
            p_success=float(p[k]),
            detail=dict(
                lane=float(lane[k]),
                interceptor=int(interceptor[k]),
                lane_s=float(lane_s[k]),
                recv_press=float(rp[k]),
                v0=float(v0[k]),
                flight=float(flight[k]),
                dist=float(dist[k]),
                into_box=bool(into_box[k]),
            ),
        )
        for k in range(len(R))
    ]


def choose(options: list[Option], vision: float, chaos: bool, rng: np.random.Generator) -> Option:
    temp = 0.0030 * (1.55 - vision) * (1.3 if chaos else 1.0)
    u = np.array([o.utility for o in options])
    w = np.exp((u - u.max()) / temp)
    w /= w.sum()
    return options[int(rng.choice(len(options), p=w))]


def cone_mask(shooter: np.ndarray, opp_pos: np.ndarray, reach: float = 0.6) -> np.ndarray:
    """Which opponents stand inside the triangle between the shooter and the goal posts.

    reach widens the triangle by a body's width (0.6 m) or, for blocks, a stretched leg.
    """
    goal = np.array([LENGTH, HALF_WIDTH])
    to_goal = goal - shooter
    dist = float(np.hypot(*to_goal))
    if dist < 1e-6 or len(opp_pos) == 0:
        return np.zeros(len(opp_pos), dtype=bool)
    rel = opp_pos - shooter
    along = rel @ (to_goal / dist)
    perp = np.abs(rel[:, 0] * to_goal[1] - rel[:, 1] * to_goal[0]) / dist
    half_width_at = reach + (3.66 / dist) * along
    return (along > 0.5) & (along < dist - 1.0) & (perp < half_width_at)


def _defenders_in_cone(shooter: np.ndarray, opp_pos: np.ndarray) -> int:
    return int(cone_mask(shooter, opp_pos).sum())


CARRY_ANGLES = np.array([0.0, 0.45, -0.45])
_STEPS = np.arange(1.0, 17.0)


def _free_run(origin: np.ndarray, opp_pos: np.ndarray, opp_speed: np.ndarray, max_len: float) -> np.ndarray:
    """How far the carrier can run in each carry direction before an opponent can get there first.

    A point on the path is free while the carrier (at about 5 m/s) would reach it at least
    0.3 s before any opponent could. Returns a length per direction in CARRY_ANGLES.
    """
    dirs = np.stack([np.cos(CARRY_ANGLES), np.sin(CARRY_ANGLES)], axis=1)  # (3, 2)
    points = origin + dirs[:, None, :] * _STEPS[None, :, None]  # (3, S, 2)
    t_carrier = _STEPS / 5.0
    d = np.linalg.norm(points[:, :, None, :] - opp_pos[None, None, :, :], axis=3)  # (3, S, O)
    t_opp = np.maximum(d - 1.0, 0.0) / np.maximum(opp_speed, 1.0)[None, None, :] + 0.2
    free = (t_opp > (t_carrier[None, :, None] + 0.3)).all(axis=2)  # (3, S)
    blocked = ~free
    first_blocked = np.where(blocked.any(axis=1), blocked.argmax(axis=1), len(_STEPS))
    return np.minimum(first_blocked.astype(float), max_len)
