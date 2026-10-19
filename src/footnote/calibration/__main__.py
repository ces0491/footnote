"""python -m footnote.calibration: generate two seasons and write docs/calibration.md."""

from __future__ import annotations

import argparse
from pathlib import Path

from footnote.calibration.report import context, measure, render, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m footnote.calibration", description=__doc__)
    parser.add_argument("--seed", type=int, default=2026, help="league seed of the first season (the default league)")
    parser.add_argument("--check-seed", type=int, default=2027, help="league seed of the second season")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, default=None, help="only the first N fixtures (for a quick look)")
    parser.add_argument("--out", type=Path, default=Path("docs/calibration.md"))
    args = parser.parse_args(argv)
    seasons = []
    physical: list[dict] = []
    seconds = 0.0
    n_matches = 0
    for seed in (args.seed, args.check_seed):
        summaries, phys, took = run(seed, args.workers, args.limit)
        seasons.append((seed, measure(summaries, phys)))
        physical += phys
        seconds += took
        n_matches = len(summaries)
    text = render(seasons, context(physical), n_matches, seconds)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"wrote {args.out} from {len(seasons)} seasons of {n_matches} matches in {seconds:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
