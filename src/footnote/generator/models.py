"""The probability models behind every simulated outcome.

These are the generator's ground truth. The simulation draws each pass, shot and
duel outcome from them, and the answer key stores the probability used, so the
models built on Day 3 can be scored against the true probability as well as the
outcome.

All positions here are in the acting team's frame (see pitch.py).
"""

from __future__ import annotations

import numpy as np

from footnote.generator.pitch import (
    HALF_WIDTH,
    LENGTH,
    SPOT_GOAL_ANGLE,
    dist_to_goal,
    goal_angle,
)


def sigmoid(x: np.ndarray | float) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.asarray(x, dtype=float)))


# ----- value of having the ball at a location ---------------------------------------------


def threat(u: np.ndarray | float, v: np.ndarray | float) -> np.ndarray:
    """Chance that possession at (u, v) ends in a goal: an expected-threat-style surface.

    Rises steeply near the goal and with the angle onto it; about 0.005 around halfway,
    0.06 at the edge of the box centrally and 0.11 at the penalty spot.
    """
    d = dist_to_goal(u, v)
    angle = np.minimum(goal_angle(u, v) / SPOT_GOAL_ANGLE, 1.6)
    return 0.004 + 0.30 * np.exp(-d / 11.0) * (0.35 + 0.65 * np.sqrt(angle))


def turnover_cost(u: np.ndarray | float, v: np.ndarray | float) -> np.ndarray:
    """Threat handed to the opponent if the ball is lost at team-frame (u, v)."""
    return threat(LENGTH - np.asarray(u, dtype=float), 2 * HALF_WIDTH - np.asarray(v, dtype=float))


# ----- passing -----------------------------------------------------------------------------


def lane_risk(
    start: np.ndarray,
    ends: np.ndarray,
    opponents: np.ndarray,
    opp_speed: np.ndarray,
    ball_speed: np.ndarray,
    lofted: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Chance that an opponent cuts out each of K candidate passes from `start`.

    For each pass and opponent: the time the ball needs to reach the point on its path
    closest to the opponent, against the time the opponent needs to get there. A lofted
    ball can only be cut out near either end of its flight.

    ends is (K, 2); ball_speed and lofted are (K,). Returns (risk, index of the likeliest
    interceptor, fraction along the path where they'd cut it out), each (K,).
    """
    k_n = len(ends)
    if k_n == 0 or len(opponents) == 0:
        return np.zeros(k_n), np.full(k_n, -1), np.zeros(k_n)
    ab = ends - start  # (K, 2)
    length2 = np.maximum(np.einsum("kd,kd->k", ab, ab), 1e-9)
    rel = opponents - start  # (O, 2)
    s = np.clip((ab @ rel.T) / length2[:, None], 0.0, 1.0)  # (K, O)
    closest = start + s[:, :, None] * ab[:, None, :]
    d = np.linalg.norm(opponents[None, :, :] - closest, axis=2)
    t_ball = s * np.sqrt(length2)[:, None] / ball_speed[:, None]
    t_def = np.maximum(d - 1.0, 0.0) / np.maximum(opp_speed, 1.0)[None, :] + 0.25
    each = sigmoid((t_ball - t_def) / 0.18)
    # Opponents level with or behind the passer can't realistically cut out the ball early.
    each = np.where(s < 0.04, each * 0.2, each)
    air = lofted[:, None] & (s >= 0.15) & (s <= 0.88)
    each = np.where(air, each * 0.05, each)
    risk = 1.0 - np.prod(1.0 - 0.85 * each, axis=1)
    k = np.argmax(each, axis=1)
    return risk, k, s[np.arange(k_n), k]


def receiver_pressure(
    receptions: np.ndarray, opponents: np.ndarray, opp_speed: np.ndarray, flight: np.ndarray
) -> np.ndarray:
    """0-1 pressure each receiver will be under when the ball arrives. receptions is (K, 2)."""
    if len(opponents) == 0:
        return np.zeros(len(receptions))
    d = np.linalg.norm(receptions[:, None, :] - opponents[None, :, :], axis=2)
    effective = d - np.maximum(opp_speed, 1.0)[None, :] * 0.55 * flight[:, None]
    return sigmoid((2.0 - effective.min(axis=1)) / 1.1)


def passer_pressure(passer: np.ndarray, opponents: np.ndarray) -> float:
    if len(opponents) == 0:
        return 0.0
    d = float(np.linalg.norm(opponents - passer, axis=1).min())
    return float(sigmoid((2.6 - d) / 0.9))


def pass_completion(
    dist: np.ndarray,
    lofted: np.ndarray,
    lane: np.ndarray,
    recv_press: np.ndarray,
    pass_press: float,
    passing: float,
    first_touch: np.ndarray,
    retention: float,
    into_box: np.ndarray,
    edge: float = 0.0,
) -> np.ndarray:
    """True completion probability of each candidate pass.

    edge is the passing team's strength advantage (quality difference plus home edge).
    """
    logit = (
        3.85
        - 0.040 * dist
        - 0.035 * np.maximum(dist - 25.0, 0.0)
        - 0.45 * lofted
        - 2.9 * lane
        - 1.6 * recv_press
        - 0.9 * pass_press
        + 1.8 * (passing - 0.6)
        + 0.8 * (first_touch - 0.6)
        - 0.35 * into_box
        + retention
        + 0.45 * edge
    )
    return sigmoid(logit)


# ----- shooting ----------------------------------------------------------------------------

# Baseline log-odds of a shot scoring, before distance, angle and the rest are counted. Tuned
# against the published goals-per-shot figure (docs/calibration.md).
XG_INTERCEPT = -0.10


def expected_goal(
    u: float,
    v: float,
    header: bool,
    pressure: float,
    blockers: int,
    one_on_one: bool,
    finishing: float,
    gk_skill: float,
    penalty: bool = False,
    direct_free_kick: bool = False,
    edge: float = 0.0,
) -> float:
    """True probability that a shot from (u, v) is scored. edge is the shooting team's strength advantage."""
    if penalty:
        return float(np.clip(0.80 + 0.10 * (finishing - 0.6) - 0.10 * (gk_skill - 0.6), 0.65, 0.92))
    d = float(dist_to_goal(u, v))
    angle = float(goal_angle(u, v))
    logit = XG_INTERCEPT - 0.13 * d + 0.60 * angle
    logit += -1.0 * header - 0.45 * pressure - 0.28 * blockers + 0.70 * one_on_one
    logit += 0.9 * (finishing - 0.6) - 0.6 * (gk_skill - 0.6) + 0.35 * edge
    if direct_free_kick:
        logit -= 0.35
    return float(np.clip(sigmoid(logit), 0.003, 0.95))


def shot_outcome_probs(xg: float, d: float, blockers_near: int, finishing: float, header: bool) -> dict[str, float]:
    """Split a shot into blocked / off target / saved / goal with P(goal) exactly xg.

    Blocks rise with defenders in the shot's path; on-target rates fall with
    distance. The goal-given-on-target rate is then whatever makes the total match
    xg, bounded so the split stays valid.
    """
    p_block = float(np.clip(0.16 + 0.20 * blockers_near, 0.0, 0.7))
    p_on = float(sigmoid(0.45 - 0.055 * d + 1.0 * (finishing - 0.6) - 0.25 * header))
    p_goal_given_on = xg / max((1.0 - p_block) * p_on, 1e-9)
    if p_goal_given_on > 0.96:
        p_goal_given_on = 0.96
        p_on = min(0.99, xg / ((1.0 - p_block) * 0.96))
        if (1.0 - p_block) * p_on * 0.96 < xg:
            p_block = max(0.0, 1.0 - xg / (0.99 * 0.96))
            p_on = 0.99
    goal = xg
    saved = (1.0 - p_block) * p_on - goal
    off = (1.0 - p_block) * (1.0 - p_on)
    return dict(blocked=p_block, off_target=max(off, 0.0), saved=max(saved, 0.0), goal=goal)


def shot_speed(dist: float, header: bool, penalty: bool, rng: np.random.Generator) -> float:
    """Ball speed off the boot (or head) in km/h."""
    if header:
        return float(np.clip(rng.normal(52.0, 9.0), 30.0, 80.0))
    if penalty:
        return float(np.clip(rng.normal(92.0, 10.0), 60.0, 125.0))
    power = np.clip(0.35 + 0.018 * dist + rng.normal(0, 0.18), 0.05, 1.0)
    return float(np.clip(55.0 + 60.0 * power + rng.normal(0, 5.0), 40.0, 130.0))


# ----- duels and fouls ---------------------------------------------------------------------


def tackle_win_prob(tackling: float, dribbling: float, press: float, support: int, edge: float = 0.0) -> float:
    """Chance a challenging defender wins the ball. edge is the defending team's strength advantage."""
    return float(sigmoid(-0.1 + 2.4 * (tackling - dribbling) + 0.4 * press + 0.25 * support + 0.4 * edge))


def foul_prob(aggression: float, tackling: float, foul_shift: float, in_own_box: bool) -> float:
    """Chance a challenge is a foul. Defenders are more careful in their own box."""
    logit = -1.3 + 1.3 * (aggression - 0.5) - 1.1 * (tackling - 0.6) + foul_shift - 2.3 * in_own_box
    return float(sigmoid(logit))


def aerial_win_prob(heading_a: float, height_a: float, heading_b: float, height_b: float) -> float:
    """Chance player a wins a header against player b."""
    return float(sigmoid(2.4 * (heading_a - heading_b) + 0.05 * (height_a - height_b)))


def ground_duel_prob(a: dict[str, float], b: dict[str, float]) -> float:
    """Chance player a comes out on top when two players challenge for the ball on the ground."""
    return float(sigmoid(1.2 * (a["dribbling"] + a["tackling"] - b["dribbling"] - b["tackling"])))
