"""The committed showcase recipe still produces the match docs/experience.md describes, and the
committed showcase files are that match.

If the generator changes, the recipe stops replaying the story: rerun
`python -m footnote.generator showcase --search` and commit the new recipe and data files.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from footnote.generator.io import write_league, write_match
from footnote.generator.league import League
from footnote.generator.season import GeneratedMatch
from footnote.generator.showcase import (
    ADEYANI,
    PENHALLOW,
    SHOWCASE_ID,
    _last_per_step,
    check_story,
    generate_showcase,
    load_recipe,
)
from footnote.generator.tracking import Tracking

DATA = Path(__file__).resolve().parents[1] / "data"
RECIPE = DATA / "showcase_recipe.json"


@pytest.fixture(scope="module")
def showcase(league: League) -> GeneratedMatch:
    if not RECIPE.exists():
        pytest.fail("data/showcase_recipe.json is missing; run python -m footnote.generator showcase --search")
    return generate_showcase(league, load_recipe(RECIPE), with_tracking=True)


def test_story_holds(showcase: GeneratedMatch) -> None:
    assert check_story(showcase) == []


def test_committed_files_are_the_replayed_match(showcase: GeneratedMatch, league: League, tmp_path: Path) -> None:
    """The deployed services read the committed files, so they must be what the recipe produces.

    If this fails after a generator change, regenerate them with `python -m footnote.generator showcase`.
    If it fails on a machine where test_story_holds also fails, the replay itself differs there; the
    committed files are still the reference.
    """
    write_league(league, tmp_path)
    write_match(showcase, tmp_path)
    for rel in (
        "league.json",
        "answer_key/league.json",
        f"answer_key/{SHOWCASE_ID}.json",
        f"matches/{SHOWCASE_ID}/meta.json",
    ):
        committed = DATA / rel
        assert committed.exists(), f"data/{rel} is missing; run python -m footnote.generator showcase"
        assert json.loads(committed.read_text(encoding="utf-8")) == json.loads(
            (tmp_path / rel).read_text(encoding="utf-8")
        ), f"data/{rel} differs from the replay"
    feed = f"matches/{SHOWCASE_ID}/feed.jsonl"
    lines = [json.loads(line) for line in (DATA / feed).read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines == showcase.output.feed, f"data/{feed} differs from the replay"
    committed_tracking = Tracking.load(str(DATA / "matches" / SHOWCASE_ID / "tracking.npz"))
    replayed = Tracking.load(str(tmp_path / "matches" / SHOWCASE_ID / "tracking.npz"))
    for field in ("period", "t", "players", "ball", "occupancy"):
        assert np.array_equal(getattr(committed_tracking, field), getattr(replayed, field), equal_nan=True), field
    assert committed_tracking.slot_players == replayed.slot_players


def test_feed_tells_the_story(showcase: GeneratedMatch) -> None:
    feed = showcase.output.feed
    goals = [m for m in feed if m["type"] == "goal"]
    assert [g["minute"] for g in goals] == [23, 31, 52, 81]
    ruled_out = [m for m in feed if m["type"] == "var_check" and m.get("decision") == "no_goal"]
    assert [m["goal_event_id"] for m in ruled_out] == [goals[1]["event_id"]]
    # The 81st-minute goal is first credited as a Penhallow own goal, then amended to Adeyani.
    winner = goals[3]
    assert winner["own_goal"] and winner["player_id"] == PENHALLOW and winner["team_id"] == "kin"
    amendment = next(m for m in feed if m["type"] == "amendment")
    assert amendment["event_id"] == winner["event_id"] and amendment["minute"] == 84
    assert amendment["changes"]["player_id"] == {"before": PENHALLOW, "after": ADEYANI}
    assert amendment["changes"]["own_goal"] == {"before": True, "after": False}
    end = next(m for m in feed if m["type"] == "match_end")
    assert end["score"] == {"home": 1, "away": 2}


def test_superseded_reseeds_are_dropped() -> None:
    assert _last_per_step([(1, 5), (9, 1), (9, 2), (12, 3)]) == [(1, 5), (9, 2), (12, 3)]
