"""Generate two seasons, measure them, and write docs/calibration.md.

The report compares match-level averages from two generated seasons (the league's 380 fixtures
under two league seeds, with tracking) against the published figures in targets.py. Each
generated mean carries a 95% interval for the simulation's own sampling noise; the published
figure is one real season, with noise of its own. The second season separates gaps that hold
under both seeds from those that come and go with one season's draws.
"""

from __future__ import annotations

import math
import time
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime

import numpy as np

from footnote.calibration.targets import CONTEXT, TARGETS, Target
from footnote.generator.league import build_league
from footnote.generator.season import GeneratedMatch, fixtures, generate_match, physical_summary, summarise
from footnote.generator.showcase import code_fingerprint

Results = dict[str, tuple[float, float | None]]
PUBLISHED = {t.key: t.value for t in TARGETS}
# The published distance range's players: outfield, 1,500 minutes or more after 29 matchweeks.
REGULARS_MINUTES = 1500
REGULARS_MATCHDAYS = 29


def _job(args: tuple[int, int]) -> tuple[dict, dict]:
    seed, index = args
    league = build_league(seed)
    fx = fixtures(league)[index]
    gm = generate_match(league, fx, with_tracking=True)
    summary = summarise(gm)
    # Yellow cards as football-data.co.uk counts English ones: a first yellow that a second turns into
    # a red isn't counted, and each second yellow follows one first yellow of the same player.
    summary["yellow_cards"] -= sum(e["type"] == "card" and e["card"] == "second_yellow" for e in gm.sim.events)
    phys = physical_summary(gm)
    phys["seed"], phys["matchday"] = seed, fx.matchday
    phys["minutes"] = {pid: _minutes_played(gm, pid) for pid in phys["players"]}
    phys["keepers"] = [pid for pid in phys["players"] if league.player(pid).role == "GK"]
    return summary, phys


def _minutes_played(gm: GeneratedMatch, pid: str) -> float:
    """Minutes a player was on the pitch, from the tracking's slot occupancy."""
    tr = gm.tracking
    assert tr is not None
    rows = np.zeros(len(tr.t), dtype=bool)
    for version, slots in enumerate(tr.slot_players):
        if pid in slots:
            slot = slots.index(pid)
            rows |= (tr.occupancy == version) & ~np.isnan(tr.players[:, slot, 0])
    return float(rows.sum()) / 10.0 / 60.0


def run(seed: int = 2026, workers: int = 8, limit: int | None = None) -> tuple[list[dict], list[dict], float]:
    league = build_league(seed)
    n = len(fixtures(league)) if limit is None else limit
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_job, [(seed, i) for i in range(n)], chunksize=2))
    return [r[0] for r in results], [r[1] for r in results], time.time() - t0


def _mean_ci(values: list[float]) -> tuple[float, float]:
    a = np.asarray(values, dtype=float)
    return float(a.mean()), float(1.96 * a.std(ddof=1) / math.sqrt(len(a))) if len(a) > 1 else 0.0


def _share_ci(k: float, n: float) -> tuple[float, float]:
    p = k / n if n else 0.0
    return p, 1.96 * math.sqrt(p * (1 - p) / n) if n else 0.0


def measure(summaries: list[dict], physical: list[dict]) -> Results:
    """Each metric as (value, half-width of its 95% interval, or None where no interval applies)."""
    s = summaries
    n = len(s)
    out: Results = {}
    per_match = {
        "goals": [m["goals"] for m in s],
        "shots": [m["shots"] for m in s],
        "shots_on_target": [m["shots_on_target"] for m in s],
        "shots_blocked": [m["shots_blocked"] for m in s],
        "corners": [m["corners"] for m in s],
        "throw_ins": [m["throw_ins"] for m in s],
        "goal_kicks": [m["goal_kicks"] for m in s],
        "fouls": [m["fouls"] for m in s],
        "offsides": [m["offsides"] for m in s],
        "yellow_cards": [m["yellow_cards"] for m in s],
        "red_cards": [m["red_cards"] for m in s],
        "penalties": [m["penalties"] for m in s],
        "own_goals": [m["own_goals"] for m in s],
        "var_overturns": [m["var_overturns"] for m in s],
        "ball_in_play_min": [m["ball_in_play_seconds"] / 60 for m in s],
        "match_minutes": [m["match_seconds"] / 60 for m in s],
        "passes_per_team": [m["home_passes"] for m in s] + [m["away_passes"] for m in s],
        "team_distance_km": [d / 1000 for p in physical for d in p["team_distance"]],
    }
    for key, values in per_match.items():
        out[key] = _mean_ci(values)
    home_goals = np.array([m["home_goals"] for m in s])
    away_goals = np.array([m["away_goals"] for m in s])
    out["home_win"] = _share_ci(float((home_goals > away_goals).sum()), n)
    out["draw"] = _share_ci(float((home_goals == away_goals).sum()), n)
    out["away_win"] = _share_ci(float((home_goals < away_goals).sum()), n)
    out["btts"] = _share_ci(float(((home_goals > 0) & (away_goals > 0)).sum()), n)
    out["nil_nil"] = _share_ci(float((home_goals + away_goals == 0).sum()), n)
    goals = sum(m["goals"] for m in s)
    out["conversion"] = _share_ci(goals, sum(m["shots"] for m in s))
    passes = sum(m["home_passes"] + m["away_passes"] for m in s)
    complete = sum(m["home_passes_complete"] + m["away_passes_complete"] for m in s)
    out["pass_completion"] = _share_ci(complete, passes)
    out["penalty_conversion"] = _share_ci(sum(m["penalty_goals"] for m in s), sum(m["penalties"] for m in s))
    out["headed_share"] = _share_ci(sum(m["headed_goals"] for m in s), goals)
    out["set_piece_share"] = _share_ci(sum(m["set_piece_goals"] for m in s), goals)
    # Club possession over the season: the club's share of the passes in its matches.
    own: dict[str, int] = defaultdict(int)
    total: dict[str, int] = defaultdict(int)
    for m in s:
        for side, other in (("home", "away"), ("away", "home")):
            own[m[side]] += m[f"{side}_passes"]
            total[m[side]] += m[f"{side}_passes"] + m[f"{other}_passes"]
    shares = sorted(own[c] / total[c] for c in own)
    out["possession_low"] = (shares[0], None)
    out["possession_high"] = (shares[-1], None)
    # Speeds: the fastest anyone ran all season, and the slowest club's fastest player.
    fastest: dict[str, float] = defaultdict(float)
    for p in physical:
        for pid, rec in p["players"].items():
            fastest[pid] = max(fastest[pid], rec["top_speed"] * 3.6)
    out["top_speed_max"] = (max(fastest.values()), None)
    by_club: dict[str, float] = defaultdict(float)
    for pid, v in fastest.items():
        club = pid.split("-")[0]
        by_club[club] = max(by_club[club], v)
    out["club_fastest_low"] = (min(by_club.values()), None)
    return out


def context(physical: list[dict]) -> dict[str, str]:
    """Generated figures for the context rows."""
    sprint = [d / 1000 for p in physical for d in p["sprint"]]
    team = [d / 1000 for p in physical for d in p["team_distance"]]
    # As the published range: each outfield player's distance per 90 over the first 29 matchdays,
    # among those with 1,500 minutes or more, lowest and highest.
    played: dict[tuple[int, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
    for p in physical:
        if p["matchday"] > REGULARS_MATCHDAYS:
            continue
        for pid, rec in p["players"].items():
            if pid not in p["keepers"]:
                totals = played[(p["seed"], pid)]
                totals[0] += rec["distance"]
                totals[1] += p["minutes"].get(pid, 0.0)
    per90 = [metres / minutes * 90 / 1000 for metres, minutes in played.values() if minutes >= REGULARS_MINUTES]
    regulars = f"outfield players with {REGULARS_MINUTES:,} minutes or more by matchday {REGULARS_MATCHDAYS}"
    return {
        "Distance per team per match, 2024/25": f"{np.mean(team):.1f} km (SD {np.std(team):.1f})",
        "Sprint distance (>7 m/s) per team per match, 2024/25": f"{np.mean(sprint):.1f} km (SD {np.std(sprint):.1f})",
        "Distance per 90 minutes, regular players, 2024/25 to Matchweek 29": (
            f"{min(per90):.1f} to {max(per90):.1f} km (lowest and highest of the {regulars}, both seasons)"
            if per90
            else f"no {regulars} in these matches"
        ),
    }


# ----- notes on the gaps, written from the figures so they stay true when the figures move ---------


def _mean(seasons: list[Results], key: str) -> float:
    return float(np.mean([r[key][0] for r in seasons]))


def _results_note(seasons: list[Results]) -> str | None:
    if max(r["draw"][0] for r in seasons) >= PUBLISHED["draw"]:
        return None
    home = 100 * (_mean(seasons, "home_win") - PUBLISHED["home_win"])
    away = 100 * (_mean(seasons, "away_win") - PUBLISHED["away_win"])
    if home > away:
        where = (
            f"Most of the difference has gone to home wins: across the seasons they average {home:+.1f} points "
            f"on the published rate, and away wins {away:+.1f}, so home advantage is stronger than in the real "
            "league."
        )
    else:
        where = (
            f"Across the seasons the difference is split between home wins ({home:+.1f} points on the "
            f"published rate) and away wins ({away:+.1f})."
        )
    return f"Draws are rarer than in the real league. {where}"


def _possession_note(seasons: list[Results]) -> str | None:
    ends = []
    if max(r["possession_low"][0] for r in seasons) < PUBLISHED["possession_low"]:
        ends.append("the club with least of the ball has less of it than any real club")
    if min(r["possession_high"][0] for r in seasons) > PUBLISHED["possession_high"]:
        ends.append("the club with most has more")
    if not ends:
        return None
    return (
        "Possession here is each club's share of the passes in its matches. The generated clubs spread wider "
        "than the real ones: " + ", and ".join(ends) + "."
    )


def _shots_note(seasons: list[Results]) -> str | None:
    shots, on, blocked = (_mean(seasons, k) for k in ("shots", "shots_on_target", "shots_blocked"))
    off = shots - on - blocked
    published_off = PUBLISHED["shots"] - PUBLISHED["shots_on_target"] - PUBLISHED["shots_blocked"]
    if off <= published_off:
        return None
    fewer = [
        kind
        for kind, mine, real in (
            ("on target", on, PUBLISHED["shots_on_target"]),
            ("blocked", blocked, PUBLISHED["shots_blocked"]),
        )
        if mine < real
    ]
    why = f", since fewer are {' or '.join(fewer)}" if fewer else ""
    return (
        f"More shots miss the target than in the real league: across the seasons, {off:.1f} a match against "
        f"{published_off:.1f}{why}."
    )


NOTES: dict[str, Callable[[list[Results]], str | None]] = {
    "draw": _results_note,
    "home_win": _results_note,
    "away_win": _results_note,
    "possession_low": _possession_note,
    "possession_high": _possession_note,
    "shots_on_target": _shots_note,
    "shots_blocked": _shots_note,
}


# ----- the report -----------------------------------------------------------------------------------


def _fmt(t: Target, v: float) -> str:
    if t.unit == "share":
        return f"{100 * v:.1f}%"
    if t.unit == "minutes":
        whole = int(v)
        return f"{whole}:{int(round((v - whole) * 60)):02d}"
    if t.unit in ("km/h", "km"):
        return f"{v:.1f} {t.unit}"
    return f"{v:.2f}" if v < 10 else f"{v:.1f}"


def _fmt_ci(t: Target, half: float | None) -> str:
    if half is None:
        return ""
    if t.unit == "share":
        return f" ± {100 * half:.1f}"
    if t.unit == "minutes":
        return f" ± {half * 60:.0f} s"
    return f" ± {half:.2f}" if half < 10 else f" ± {half:.1f}"


def _gap(t: Target, v: float) -> int:
    """Difference from the published figure in whole percent, as the table shows it."""
    return round(100 * (v - t.value) / t.value) if t.value else 0


def _spread(gaps: list[int]) -> str:
    """Where a figure stands against the 10% line across the seasons: "within" it under every seed,
    "consistent" (beyond it under every seed, the same way), "opposite" (beyond it under every seed,
    both ways) or "some" (beyond it under some seeds only)."""
    if max(abs(g) for g in gaps) <= 10:
        return "within"
    if min(abs(g) for g in gaps) <= 10:
        return "some"
    return "consistent" if all(g > 0 for g in gaps) or all(g < 0 for g in gaps) else "opposite"


_WORDS = {1: "one", 2: "two", 3: "three", 4: "four"}


def render(seasons: list[tuple[int, Results]], ctx: dict[str, str], n_matches: int, seconds: float) -> str:
    """The report for generated seasons given as (league seed, measured results)."""
    seeds = [seed for seed, _ in seasons]
    results = [r for _, r in seasons]
    rows = []
    for t in TARGETS:
        generated = " | ".join(f"{_fmt(t, r[t.key][0])}{_fmt_ci(t, r[t.key][1])}" for r in results)
        diffs = " / ".join(f"{_gap(t, r[t.key][0]):+d}%" for r in results)
        rows.append(
            f"| {t.label} | {generated} | {_fmt(t, t.value)} | {diffs} | [{t.source}]({t.url}) | {t.derivation} |"
        )
    ctx_rows = [
        f"| {label} | {ctx.get(label, '')} | {published} | [{source}]({url}) |"
        for label, published, source, url in CONTEXT
    ]
    # Gaps in whole percent, as the table shows them, so the lists below agree with the table.
    gaps = {t.key: [_gap(t, r[t.key][0]) for r in results] for t in TARGETS}
    spread = {t.key: _spread(gaps[t.key]) for t in TARGETS}
    within_10 = sum(spread[t.key] == "within" for t in TARGETS)
    within_20 = sum(max(abs(g) for g in gaps[t.key]) <= 20 for t in TARGETS)
    consistent = sorted(
        (t for t in TARGETS if spread[t.key] == "consistent"), key=lambda t: -min(abs(g) for g in gaps[t.key])
    )
    opposite = [t for t in TARGETS if spread[t.key] == "opposite"]
    varying = [t for t in TARGETS if spread[t.key] == "some"]
    gap_lines = [
        f"- {t.label}: generated {' and '.join(_fmt(t, r[t.key][0]) for r in results)}, published {_fmt(t, t.value)}."
        for t in consistent
    ]
    notes: list[str] = []
    for t in consistent:
        note_of = NOTES.get(t.key)
        note = note_of(results) if note_of else None
        if note and note not in notes:
            notes.append(note)

    def listed(targets: list[Target]) -> str:
        return ", ".join(f"{t.label.lower()} ({' / '.join(f'{g:+d}%' for g in gaps[t.key])})" for t in targets)

    varying_text, opposite_text = listed(varying), listed(opposite)
    seeds_text = " and ".join(str(s) for s in seeds)
    n_seasons = _WORDS.get(len(seeds), str(len(seeds)))
    every = "both seeds" if len(seeds) == 2 else "every seed"
    some = "under one seed but not the other" if len(seeds) == 2 else "under some seeds but not all"
    today = datetime.now(UTC).date().isoformat()
    return "\n".join(
        [
            "# Calibration",
            "",
            "How closely generated seasons match a real one. The generator was tuned against the published",
            f"figures below. This report measures {n_seasons} full generated seasons, under league seeds {seeds_text},",
            f"which separates the gaps that hold under {every} from those that come and go with one",
            "season's draws.",
            "",
            f"Generated on {today}: all {n_matches} fixtures of the 2026/27 season under each seed, with 10 Hz",
            f"tracking, in {seconds / 60:.0f} minutes. Generator fingerprint `{code_fingerprint()}`. Regenerate with",
            "`python -m footnote.calibration`.",
            "",
            "Published figures are for the 2025/26 Premier League season unless the row says otherwise.",
            '"±" is the 95% interval of the generated mean from the simulation\'s own sampling noise;',
            "the published figure is a single real season and is noisy too.",
            "",
            "| Metric | " + " | ".join(f"Generated, seed {s}" for s in seeds) + " | Published | Difference | Source "
            "| How the published figure was obtained |",
            "| --- | " + " | ".join("---" for _ in seeds) + " | --- | --- | --- | --- |",
            *rows,
            "",
            "## Largest differences",
            "",
            f"{within_10} of the {len(TARGETS)} figures are within 10% of the published value under {every}, and "
            f"{within_20} within 20%.",
            "",
            *(
                [f"More than 10% off under {every}, in the same direction, furthest first:", "", *gap_lines, ""]
                if gap_lines
                else []
            ),
            *[line for note in notes for line in (note, "")],
            *([f"More than 10% off under {every}, in opposite directions: {opposite_text}.", ""] if opposite else []),
            *([f"More than 10% off {some}: {varying_text}.", ""] if varying else []),
            "## Physical figures for context",
            "",
            "These published figures describe a different season, or were read from a chart rather than text,",
            "so they are shown beside the generated figures, pooled over both seasons, without being used as",
            "targets.",
            "",
            "| Metric | Generated | Published | Source |",
            "| --- | --- | --- | --- |",
            *ctx_rows,
            "",
            "## Sources",
            "",
            "Results, shots on target, fouls, corners and yellow cards are counted from football-data.co.uk's",
            "2025/26 match file. Figures sourced to premierleague.com's club stats are the 20 clubs' 2025/26",
            "season totals, summed, read from the data behind the site's club stats pages; the sums match Opta",
            "Analyst's published season totals where both exist (1,045 goals, 9,503 shots, 273,956 successful",
            "passes, 44 red cards, 13,615 throw-ins, 5,901 goal kicks).",
            "The VAR count is from ModernGhana's republication of the BBC Sport article; the BBC original",
            "wasn't read. Quotes and sums were checked against the sources on 2026-10-19.",
            "",
        ]
    )
