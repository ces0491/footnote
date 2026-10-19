"""Command line: python -m footnote.generator <command>.

league      write the league (public data and its answer key)
match       generate one match between two clubs
season      generate the season's fixtures, in parallel
showcase    replay the showcase recipe, or search for a new one with --search
schema      print the feed's JSON Schema
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from footnote.generator import showcase
from footnote.generator.io import write_league, write_match
from footnote.generator.league import build_league
from footnote.generator.schema import feed_json_schema
from footnote.generator.season import Fixture, fixtures, generate_match

DEFAULT_SEED = 2026
DEFAULT_OUT = Path("data")
RECIPE_PATH = Path("data/showcase_recipe.json")


def _season_job(args: tuple[int, Fixture, str, bool]) -> str:
    seed, fixture, out_dir, with_tracking = args
    league = build_league(seed)
    gm = generate_match(league, fixture, with_tracking=with_tracking)
    write_match(gm, Path(out_dir))
    return fixture.match_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m footnote.generator", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="league seed (default %(default)s)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory (default %(default)s)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("league")
    m = sub.add_parser("match")
    m.add_argument("home", help="home club code, e.g. SAL")
    m.add_argument("away", help="away club code, e.g. KIN")
    m.add_argument("--match-id", default=None)
    m.add_argument("--tracking", action="store_true", help="also write 10 Hz tracking")
    s = sub.add_parser("season")
    s.add_argument("--limit", type=int, default=None, help="only the first N fixtures")
    s.add_argument("--workers", type=int, default=8)
    s.add_argument("--tracking", action="store_true")
    sc = sub.add_parser("showcase")
    sc.add_argument("--search", action="store_true", help="search for a new recipe instead of replaying")
    sc.add_argument("--root", type=int, default=1, help="root seed for the search")
    sc.add_argument("--recipe", type=Path, default=RECIPE_PATH)
    sub.add_parser("schema")
    args = parser.parse_args(argv)

    if args.command == "schema":
        print(json.dumps(feed_json_schema(), indent=1))
        return 0

    league = build_league(args.seed)
    out: Path = args.out
    if args.command == "league":
        write_league(league, out)
        print(f"wrote league to {out}")
        return 0

    if args.command == "match":
        mid = args.match_id or f"fl-2627-x-{args.home.lower()}-{args.away.lower()}"
        fx = Fixture(
            matchday=0, home=args.home.upper(), away=args.away.upper(), kickoff=datetime(2026, 8, 15, 14, 0, tzinfo=UTC)
        )
        gm = generate_match(league, fx, with_tracking=args.tracking, match_id=mid)
        path = write_match(gm, out)
        print(f"{mid}: {gm.sim.s.score[0]}-{gm.sim.s.score[1]}, {len(gm.output.feed)} messages -> {path}")
        return 0

    if args.command == "season":
        write_league(league, out)
        season_fixtures = fixtures(league)[: args.limit] if args.limit else fixtures(league)
        t0 = time.time()
        jobs = [(args.seed, f, str(out), args.tracking) for f in season_fixtures]
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for i, mid in enumerate(pool.map(_season_job, jobs, chunksize=2), start=1):
                if i % 20 == 0 or i == len(jobs):
                    print(f"  {i}/{len(jobs)} {mid}")
        print(f"season: {len(jobs)} matches in {time.time() - t0:.0f} s -> {out}")
        return 0

    if args.command == "showcase":
        if args.search:
            print("searching for the showcase match, beat by beat:")
            t0 = time.time()
            recipe = showcase.search(league, root=args.root)
            showcase.save_recipe(recipe, args.recipe)
            print(f"recipe written to {args.recipe} after {time.time() - t0:.0f} s")
        if not args.recipe.exists():
            print(f"no recipe at {args.recipe}; run with --search first", file=sys.stderr)
            return 1
        recipe = showcase.load_recipe(args.recipe)
        if recipe.get("code_fingerprint") != showcase.code_fingerprint():
            print("warning: the generator has changed since this recipe was found; checking the story", file=sys.stderr)
        gm = showcase.generate_showcase(league, recipe)
        problems = showcase.check_story(gm)
        if problems:
            print("the recipe no longer tells the story: " + "; ".join(problems), file=sys.stderr)
            print("run: python -m footnote.generator showcase --search", file=sys.stderr)
            return 1
        write_league(league, out)
        path = write_match(gm, out)
        print(f"showcase {gm.sim.s.score[0]}-{gm.sim.s.score[1]}, story checks pass -> {path}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
