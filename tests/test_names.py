"""Every name in the league has been checked against Wikidata and none belongs to a real footballer,
club or (for people) anyone at all. The check itself needs the network; see scripts/check_names.py."""

import json
from pathlib import Path

from footnote.generator.league import League

CHECK = Path(__file__).resolve().parents[1] / "data" / "name_check.json"


def test_every_name_was_checked(league: League) -> None:
    record = json.loads(CHECK.read_text(encoding="utf-8"))
    checked = set(record["names"])
    people = {n for kind, n in league.all_names() if kind != "club"}
    clubs = {c.spec.name for c in league.clubs} | {c.spec.short_name for c in league.clubs}
    missing = (people | clubs) - checked
    assert not missing, f"run scripts/check_names.py; unchecked names: {sorted(missing)[:10]}"


def test_no_name_belongs_to_a_real_footballer_or_club(league: League) -> None:
    record = json.loads(CHECK.read_text(encoding="utf-8"))
    collisions = [n for n, r in record["names"].items() if r["status"] == "collision"]
    assert not collisions
    people = {n for kind, n in league.all_names() if kind != "club"}
    namesakes = [n for n in people if record["names"][n]["status"] != "clear"]
    assert not namesakes
