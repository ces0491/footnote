"""The committed showcase match, as the live services read it.

The services deploy the files committed under data/ (league, match metadata and feed, and for the
processor the tracking); nothing regenerates them in the cloud. FOOTNOTE_DATA_DIR points at that
directory inside a container; locally it defaults to the repository's data/. The answer key is
never read here.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

SHOWCASE_MATCH_ID = "fl-2627-showcase-sal-kin"


def data_dir() -> Path:
    configured = os.environ.get("FOOTNOTE_DATA_DIR")
    return Path(configured) if configured else Path(__file__).resolve().parents[3] / "data"


@dataclass(frozen=True)
class Match:
    match_id: str
    meta: dict
    feed: list[dict]

    @property
    def home_id(self) -> str:
        return str(self.meta["home"]["id"])

    @property
    def away_id(self) -> str:
        return str(self.meta["away"]["id"])


def load_match(match_id: str = SHOWCASE_MATCH_ID, root: Path | None = None) -> Match:
    match_dir = (root or data_dir()) / "matches" / match_id
    meta = json.loads((match_dir / "meta.json").read_text(encoding="utf-8"))
    with (match_dir / "feed.jsonl").open(encoding="utf-8") as fh:
        feed = [json.loads(line) for line in fh if line.strip()]
    if [m["seq"] for m in feed] != list(range(1, len(feed) + 1)):
        raise ValueError(f"{match_dir / 'feed.jsonl'}: seq must run from 1 in publication order")
    return Match(match_id=match_id, meta=meta, feed=feed)
