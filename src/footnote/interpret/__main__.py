"""python -m footnote.interpret: fit the models, score them on held-out styles, write params and docs/models.md.

With --report-only, rewrite docs/models.md from the scores the last fit saved, without fitting.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from footnote.interpret import difficulty, state
from footnote.interpret.report import render
from footnote.interpret.train import run, write_params

SCORES = difficulty.PARAMS.with_name("scores.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m footnote.interpret", description=__doc__)
    parser.add_argument("--seed", type=int, default=2026, help="league seed (the default league)")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--report", type=Path, default=Path("docs/models.md"))
    parser.add_argument("--report-only", action="store_true", help="rewrite the report from the saved scores")
    args = parser.parse_args(argv)
    if args.report_only:
        scores = json.loads(SCORES.read_text(encoding="utf-8"))
    else:
        result = run(args.seed, args.workers)
        fitted = {k: v for k, v in result["meta"].items() if k != "seconds"}
        write_params(difficulty.PARAMS, result["difficulty"][0], fitted)
        write_params(state.PARAMS, result["state"][0], fitted)
        scores = {
            "meta": result["meta"],
            "difficulty": result["difficulty"][1],
            "state": result["state"][1] | {k: result["state"][0][k] for k in ("smoothing", "hold")},
        }
        SCORES.write_text(json.dumps(scores, indent=1) + "\n", encoding="utf-8", newline="\n")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render(scores), encoding="utf-8", newline="\n")
    print(f"wrote {args.report}" + ("" if args.report_only else f", the parameters and {SCORES}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
