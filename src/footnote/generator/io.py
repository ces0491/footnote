"""Writing league and match data to disk.

Layout under the output directory:

    league.json                 public league data: clubs, squads, officials
    matches/<match_id>/
        meta.json               match information and lineups
        feed.jsonl              the event feed, one message per line
        tracking.npz            10 Hz player and ball positions (when requested)
    answer_key/
        league.json             club quality, styles and player attributes
        <match_id>.json         regime timeline, true probabilities, provider errors

Services that play the feed read only `league.json` and `matches/`. The answer
key is for scoring models and is kept in its own directory so it can't be
shipped by accident.
"""

from __future__ import annotations

import json
from pathlib import Path

from footnote.generator.league import League
from footnote.generator.season import GeneratedMatch


def _dump(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # LF on every platform, so a file regenerated on Windows matches the one in git byte for byte.
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def write_league(league: League, out_dir: Path) -> None:
    _dump(out_dir / "league.json", league.public())
    _dump(out_dir / "answer_key" / "league.json", league.hidden())


def write_match(gm: GeneratedMatch, out_dir: Path) -> Path:
    out = gm.output
    match_dir = out_dir / "matches" / out.meta["match_id"]
    match_dir.mkdir(parents=True, exist_ok=True)
    _dump(match_dir / "meta.json", out.meta)
    with (match_dir / "feed.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for msg in out.feed:
            fh.write(json.dumps(msg, ensure_ascii=False, separators=(",", ":")))
            fh.write("\n")
    if gm.tracking is not None:
        gm.tracking.save(str(match_dir / "tracking.npz"))
    _dump(out_dir / "answer_key" / f"{out.meta['match_id']}.json", out.answer_key)
    return match_dir


def read_feed(match_dir: Path) -> list[dict]:
    with (match_dir / "feed.jsonl").open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]
