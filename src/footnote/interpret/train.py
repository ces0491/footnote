"""Fit the models on generated matches and score them on styles they never saw.

`python -m footnote.interpret` generates the league's 380 fixtures in memory, builds the evidence
the services compute (dataset.py), fits both models, scores them against the answer key, and
writes params/difficulty.json, params/state.json and docs/models.md.

The split is by playing style (dataset.py). Matches involving a club from a held-out archetype are
the test set and are used for nothing but the scores. The other matches fit the models, except
those on the last eight matchdays, which first choose how the state estimate is steadied for
display and then join the final fit.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from footnote.generator.league import League, build_league
from footnote.generator.season import Fixture, fixtures
from footnote.generator.showcase import AWAY, HOME, code_fingerprint, mt
from footnote.interpret import difficulty, state
from footnote.interpret.dataset import (
    HELD_OUT_ARCHETYPES,
    MatchRows,
    StateRows,
    StateTrace,
    match_rows,
    trace,
    trace_feed,
)
from footnote.interpret.fit import FittedNetwork, binary_logistic, softmax_network
from footnote.interpret.frames import Frames
from footnote.interpret.physical import Tracking
from footnote.interpret.state import LABELS, MIRROR_LABELS, Shown, StateModel, mirror
from footnote.live.match import SHOWCASE_MATCH_ID, data_dir, load_match

LAG = 5  # seconds the state estimate runs behind play
FIT_EVERY = 12  # seconds between the rows the network is fitted on; neighbours are near-duplicates
L2 = 1e-4
UNITS = 48  # hidden units in the state network
STATE_ITERATIONS = 1000
# Smoothing weights and holds tried on the validation matches. Of the settings whose macro F1 is
# within STEADY_COST of the best, the one whose shown state changes least often is kept.
SMOOTHINGS = (0.0, 0.5, 0.7, 0.8)
HOLDS = (0, 3, 5, 8, 12)
STEADY_COST = 0.02
SPELL_SECONDS = 60  # a spell shorter than this isn't counted in the spell detection rates
N_STATES = len(LABELS)


# ----- generating the rows, in parallel -------------------------------------------------------


def _rows_job(args: tuple[int, Fixture]) -> MatchRows:
    seed, fixture = args
    return match_rows(build_league(seed), fixture, LAG, FIT_EVERY)


def _trace_job(args: tuple[int, Fixture, StateModel]) -> StateTrace:
    seed, fixture, model = args
    return trace(build_league(seed), fixture, model)


def _parallel(fn: Callable, jobs: list, workers: int) -> list:
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(fn, jobs, chunksize=2))


# ----- pass difficulty ---------------------------------------------------------------------------


def _logloss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z))


@dataclass
class _Passes:
    x: np.ndarray
    y: np.ndarray
    truth: np.ndarray
    held_side: np.ndarray  # True for a pass by a club from a held-out archetype


def _passes(rows: list[MatchRows], held: set[str]) -> _Passes:
    xs, ys, ts, hs = [], [], [], []
    for r in rows:
        p = r.passes
        xs.append(p.x)
        ys.append(p.complete)
        ts.append(p.truth)
        codes = np.where(p.side == 0, r.home, r.away)
        hs.append(np.isin(codes, list(held)))
    return _Passes(np.vstack(xs), np.concatenate(ys), np.concatenate(ts), np.concatenate(hs))


def _kinds(x: np.ndarray) -> dict[str, np.ndarray]:
    f = difficulty.FEATURES

    def col(name: str) -> np.ndarray:
        return x[:, f.index(name)] == 1

    kinds = {"Throw-ins": col("throw_in"), "Crosses": col("cross")}
    kinds["Headed passes"] = col("header") & ~kinds["Crosses"]
    kinds["Other set pieces"] = (col("free_kick") | col("corner") | col("goal_kick") | col("kick_off")) & ~(
        kinds["Crosses"] | kinds["Headed passes"]
    )
    taken = np.any(np.stack(list(kinds.values())), axis=0)
    kinds["Lofted passes in open play"] = col("lofted") & ~taken
    kinds["Ground passes in open play"] = ~(taken | kinds["Lofted passes in open play"])
    return kinds


def fit_difficulty(rows: list[MatchRows], held: set[str]) -> tuple[dict, dict]:
    train = _passes([r for r in rows if r.split != "test"], held)
    test = _passes([r for r in rows if r.split == "test"], held)
    full = binary_logistic(train.x, train.y, L2)
    n_feed = difficulty.FEATURES.index("passer_space")
    feed_only = binary_logistic(train.x[:, :n_feed], train.y, L2)
    p = _sigmoid(full.logits(test.x)[:, 0])
    p_feed = _sigmoid(feed_only.logits(test.x[:, :n_feed])[:, 0])
    base = np.full_like(test.y, train.y.mean())

    def scores(pred: np.ndarray, sel: np.ndarray | None = None) -> dict:
        s = slice(None) if sel is None else sel
        return {
            "log_loss": _logloss(pred[s], test.y[s]),
            "brier": float(np.mean((pred[s] - test.y[s]) ** 2)),
            "mae_truth": float(np.mean(np.abs(pred[s] - test.truth[s]))),
        }

    edges = np.quantile(p, np.linspace(0, 1, 11))
    decile = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, 9)
    evaluation = {
        "train_passes": int(len(train.y)),
        "test_passes": int(len(test.y)),
        "iterations": full.iterations,
        "overall": {
            "constant": scores(base),
            "feed_only": scores(p_feed),
            "full": scores(p),
            "truth": scores(test.truth),
        },
        "calibration": [
            {
                "predicted": float(p[decile == d].mean()),
                "observed": float(test.y[decile == d].mean()),
                "truth": float(test.truth[decile == d].mean()),
                "passes": int(np.sum(decile == d)),
            }
            for d in range(10)
        ],
        "kinds": {
            name: {
                "passes": int(sel.sum()),
                "observed": float(test.y[sel].mean()),
                "predicted": float(p[sel].mean()),
                "model": scores(p, sel),
                "truth": scores(test.truth, sel),
            }
            for name, sel in _kinds(test.x).items()
        },
        "sides": {
            name: {
                "passes": int(sel.sum()),
                "observed": float(test.y[sel].mean()),
                "predicted": float(p[sel].mean()),
                "model": scores(p, sel),
                "truth": scores(test.truth, sel),
            }
            for name, sel in (("held_out", test.held_side), ("opponents", ~test.held_side))
        },
        "coefficients": dict(zip(difficulty.FEATURES, full.coef[:, 0].round(4).tolist(), strict=True)),
    }
    params = {
        "features": list(difficulty.FEATURES),
        "mean": full.mean.tolist(),
        "scale": full.scale.tolist(),
        "coef": full.coef[:, 0].tolist(),
        "intercept": float(full.intercept[0]),
    }
    return params, evaluation


# ----- the match state ---------------------------------------------------------------------------


def _fit_classifier(fit_rows: list[StateRows], val_rows: list[StateRows]) -> FittedNetwork:
    """Fit on the fitting matches' rows (already one every FIT_EVERY seconds) and every FIT_EVERYth
    second of any validation matches, each row also seen with home and away swapped."""
    x = np.vstack([s.x for s in fit_rows] + [s.x[::FIT_EVERY] for s in val_rows])
    y = np.concatenate([s.label for s in fit_rows] + [s.label[::FIT_EVERY] for s in val_rows])
    xa = np.vstack([x, mirror(x)]).astype(np.float64)
    ya = np.concatenate([y, np.array(MIRROR_LABELS)[y]])
    return softmax_network(xa, ya, N_STATES, UNITS, L2, max_iter=STATE_ITERATIONS)


def smooth(probs: np.ndarray, period: np.ndarray, restart: np.ndarray, weight: float) -> np.ndarray:
    """StateModel.step over precomputed classifier outputs: restart at each period and after a goal."""
    out = np.empty_like(probs)
    for i in range(len(probs)):
        fresh = i == 0 or period[i] != period[i - 1] or restart[i]
        out[i] = probs[i] if fresh else weight * out[i - 1] + (1.0 - weight) * probs[i]
    return out


def shown_states(belief: np.ndarray, period: np.ndarray, restart: np.ndarray, hold: int) -> np.ndarray:
    """The tracker's shown state over precomputed estimates (Shown.update, second by second)."""
    out = np.empty(len(belief), dtype=np.int64)
    shown = Shown()
    likeliest = belief.argmax(axis=1)
    for i in range(len(belief)):
        if i == 0 or period[i] != period[i - 1]:
            shown = Shown()
        out[i] = shown.update(int(likeliest[i]), hold, bool(restart[i]))
    return out


def _model(clf: FittedNetwork, smoothing: float, hold: int) -> StateModel:
    return StateModel(
        lag=LAG,
        mean=clf.mean,
        scale=clf.scale,
        hidden=clf.hidden,
        hidden_bias=clf.hidden_bias,
        coef=clf.coef,
        intercept=clf.intercept,
        smoothing=smoothing,
        hold=hold,
    )


def label_changes(pred: np.ndarray, period: np.ndarray) -> int:
    return int(np.sum((pred[1:] != pred[:-1]) & (period[1:] == period[:-1])))


def scores(pred: np.ndarray, true: np.ndarray) -> dict:
    conf = np.zeros((N_STATES, N_STATES), dtype=np.int64)
    np.add.at(conf, (true, pred), 1)
    recall = conf.diagonal() / np.maximum(conf.sum(axis=1), 1)
    precision = conf.diagonal() / np.maximum(conf.sum(axis=0), 1)
    f1 = np.where(recall + precision > 0, 2 * recall * precision / np.maximum(recall + precision, 1e-12), 0.0)
    side = np.array([0, 0, 1, 2, 1, 2, 1, 2])  # neither, home, away
    return {
        "seconds": int(len(true)),
        "accuracy": float(np.mean(pred == true)),
        "macro_f1": float(f1.mean()),
        "on_top": float(np.mean(side[pred] == side[true])),
        "recall": dict(zip(LABELS, recall.round(4).tolist(), strict=True)),
        "precision": dict(zip(LABELS, precision.round(4).tolist(), strict=True)),
        "confusion": conf.tolist(),
    }


def _spells(seq: np.ndarray) -> list[tuple[int, int, int]]:
    """(label, start, stop) runs of a per-second label sequence."""
    change = np.flatnonzero(np.diff(seq)) + 1
    starts = np.concatenate([[0], change])
    stops = np.concatenate([change, [len(seq)]])
    return [(int(seq[a]), int(a), int(b)) for a, b in zip(starts, stops, strict=True)]


def detection(traces: list[StateTrace]) -> dict:
    """How many true spells the live label catches.

    A control, pressure or chaos spell of SPELL_SECONDS or more counts as caught when the label agrees
    for at least half its seconds; a break counts as caught when any of its seconds is labelled as
    that side's break.
    """
    kinds = {"control": (2, 3), "pressure": (4, 5), "chaos": (1,), "transition": (6, 7)}
    caught = {k: [0, 0] for k in kinds}
    for tr in traces:
        pred = tr.shown
        for period in (1, 2):
            sel = tr.period == period
            truth, guess = tr.label[sel], pred[sel]
            for label, a, b in _spells(truth):
                kind = next((k for k, ls in kinds.items() if label in ls), None)
                if kind is None:
                    continue
                if kind == "transition":
                    hit = bool(np.any(guess[a:b] == label))
                elif b - a >= SPELL_SECONDS:
                    hit = bool(np.mean(guess[a:b] == label) >= 0.5)
                else:
                    continue
                caught[kind][0] += hit
                caught[kind][1] += 1
    return {k: {"caught": c, "spells": n} for k, (c, n) in caught.items()}


def fit_state(rows: list[MatchRows], league: League, workers: int, log: Callable[[str], None]) -> tuple[dict, dict]:
    fit_rows = [r.state for r in rows if r.split == "fit" and r.state is not None]
    val_rows = [r.state for r in rows if r.split == "validate" and r.state is not None]

    clf = _fit_classifier(fit_rows, [])
    log(f"  classifier on {len(fit_rows)} fitting matches: {clf.iterations} iterations")
    probs = [clf.proba(s.x.astype(np.float64)) for s in val_rows]
    truth = np.concatenate([s.label for s in val_rows])
    tuning = []
    for weight in SMOOTHINGS:
        smoothed = [smooth(p, s.period, s.restart, weight) for p, s in zip(probs, val_rows, strict=True)]
        for hold in HOLDS:
            shown = [shown_states(b, s.period, s.restart, hold) for b, s in zip(smoothed, val_rows, strict=True)]
            changes = sum(label_changes(pred, s.period) for pred, s in zip(shown, val_rows, strict=True))
            result = scores(np.concatenate(shown), truth)
            tuning.append({"smoothing": weight, "hold": hold, "changes_per_match": changes / len(val_rows), **result})
    best_f1 = max(t["macro_f1"] for t in tuning)
    chosen = min((t for t in tuning if t["macro_f1"] >= best_f1 - STEADY_COST), key=lambda t: t["changes_per_match"])
    true_changes = sum(label_changes(s.label, s.period) for s in val_rows) / len(val_rows)
    validation = {
        "matches": len(val_rows),
        "true_changes_per_match": true_changes,
        "tuning": [
            {k: t[k] for k in ("smoothing", "hold", "accuracy", "macro_f1", "on_top", "changes_per_match")}
            for t in tuning
        ],
        "chosen": {"smoothing": chosen["smoothing"], "hold": chosen["hold"]},
    }
    log(f"  smoothing {chosen['smoothing']} and hold {chosen['hold']} s chosen on {len(val_rows)} validation matches")

    clf = _fit_classifier(fit_rows, val_rows)
    model = _model(clf, chosen["smoothing"], chosen["hold"])
    log("  final classifier fitted; tracing the test matches")
    test_fixtures = [f for f in fixtures(league) if _split(rows, f) == "test"]
    traces = _parallel(_trace_job, [(league.seed, f, model) for f in test_fixtures], workers)
    showcase = _showcase(model)

    pred = np.concatenate([t.shown for t in traces])
    truth = np.concatenate([t.label for t in traces])
    classifier = np.concatenate([t.classifier for t in traces])
    rule = np.concatenate([t.rule for t in traces])
    archetype = {c.spec.code: c.spec.archetype for c in league.clubs}
    by_archetype = {}
    for name in HELD_OUT_ARCHETYPES:
        group = [t for t in traces if name in (archetype[t.home], archetype[t.away])]
        by_archetype[name] = scores(
            np.concatenate([t.shown for t in group]), np.concatenate([t.label for t in group])
        ) | {"matches": len(group)}
    live_changes = sum(label_changes(t.shown, t.period) for t in traces) / len(traces)
    true_changes = sum(label_changes(t.label, t.period) for t in traces) / len(traces)
    evaluation = {
        "lag": LAG,
        "fit_matches": len(fit_rows),
        "validation": validation,
        "test_matches": len(traces),
        "test": {
            "always_balanced": scores(np.zeros_like(truth), truth),
            "possession_rule": scores(rule, truth),
            "classifier": scores(classifier, truth),
            "live": scores(pred, truth),
        },
        "changes_per_match": {"live": live_changes, "true": true_changes},
        "true_shares": (np.bincount(truth, minlength=N_STATES) / len(truth)).round(4).tolist(),
        "by_archetype": by_archetype,
        "detection": detection(traces),
        "showcase": showcase,
    }
    params = {
        "features": list(state.FEATURES),
        "labels": list(LABELS),
        "lag": LAG,
        "mean": clf.mean.tolist(),
        "scale": clf.scale.tolist(),
        "hidden": clf.hidden.tolist(),
        "hidden_bias": clf.hidden_bias.tolist(),
        "coef": clf.coef.tolist(),
        "intercept": clf.intercept.tolist(),
        "smoothing": model.smoothing,
        "hold": model.hold,
    }
    return params, evaluation


def _split(rows: list[MatchRows], fixture: Fixture) -> str:
    return next(r.split for r in rows if r.match_id == fixture.match_id)


def _showcase(model: StateModel) -> dict:
    """The live estimate over the committed showcase match, against its answer key and its story."""
    match = load_match()
    root = data_dir()
    answer_key = json.loads((root / "answer_key" / f"{SHOWCASE_MATCH_ID}.json").read_text(encoding="utf-8"))
    tracking = Tracking.load(root / "matches" / SHOWCASE_MATCH_ID / "tracking.npz")
    tr = trace_feed(match.match_id, HOME, AWAY, match.feed, answer_key, Frames.from_meta(match.meta), tracking, model)
    pred = tr.shown
    beats = []
    # The beats the story names a state for, over the windows its checks use (generator/showcase.py).
    for name, (period, a), (_, b), label in (
        ("0-21'", mt(0), mt(21), "control:home"),
        ("38-45'", mt(38), mt(44, 59), "pressure:home"),
        ("63-68'", mt(63), mt(68), "chaos"),
    ):
        sel = (tr.period == period) & (tr.second >= a) & (tr.second < b)
        k = LABELS.index(label)
        beats.append(
            {
                "beat": name,
                "state": label,
                "truth_share": float(np.mean(tr.label[sel] == k)),
                "model_share": float(np.mean(pred[sel] == k)),
                "agreement": float(np.mean(pred[sel] == tr.label[sel])),
            }
        )
    # The break that ended in the first goal: the away side's true break spell running into it.
    goal = next(m for m in match.feed if m["type"] == "goal")
    first = tr.period == goal["period"]
    breaking = LABELS.index("transition:away")
    spells = [(a, b) for lab, a, b in _spells(tr.label[first]) if lab == breaking and a <= goal["t"] <= b + 5]
    caught = [bool(np.any(pred[first][a:b] == breaking)) for a, b in spells]
    return {"overall": scores(pred, tr.label), "beats": beats, "first_goal_break": caught}


# ----- writing it out ----------------------------------------------------------------------------


def write_params(path: Path, params: dict, meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**params, "fitted": meta}, indent=1) + "\n", encoding="utf-8", newline="\n")


def run(seed: int, workers: int, log: Callable[[str], None] = print) -> dict:
    t0 = time.time()
    league = build_league(seed)
    held = {c.spec.code for c in league.clubs if c.spec.archetype in HELD_OUT_ARCHETYPES}
    log(f"generating {len(fixtures(league))} matches with tracking")
    rows = _parallel(_rows_job, [(seed, f) for f in fixtures(league)], workers)
    counts = {s: sum(r.split == s for r in rows) for s in ("fit", "validate", "test")}
    log(f"  {counts} in {time.time() - t0:.0f} s")
    log("pass difficulty")
    difficulty_params, difficulty_eval = fit_difficulty(rows, held)
    log("match state")
    state_params, state_eval = fit_state(rows, league, workers, log)
    meta = {
        "by": "python -m footnote.interpret",
        "date": datetime.now(UTC).date().isoformat(),
        "league_seed": seed,
        "generator": code_fingerprint(),
        "held_out_archetypes": list(HELD_OUT_ARCHETYPES),
        "held_out_clubs": sorted(held),
        "matches": counts,
    }
    return {
        "meta": meta | {"seconds": round(time.time() - t0)},
        "difficulty": (difficulty_params, difficulty_eval),
        "state": (state_params, state_eval),
    }
