"""Check every name the league uses against Wikidata, and record the result in data/name_check.json.

The hackathon requires fictional clubs and players. This looks for exact matches:

- people (instance of human) whose label equals a player's or official's full name, noting
  whether they are footballers;
- items of any kind whose label equals a club's name or its place name.

A match with a footballer or a football club is a collision and fails tests/test_names.py.
Other matches (a real person with the same name who isn't a footballer, a real village) are
recorded as cautions for a human to judge. Wikidata doesn't list every lower-league player,
so a clear result can still miss one; the showcase cast was also checked by web search.

Usage: uv run python scripts/check_names.py [--seed 2026]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from footnote.generator.league import build_league

ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "footnote-namecheck/0.1 (https://github.com/ces0491/footnote)"
FOOTBALLER = "Q937857"
OUT = Path("data/name_check.json")


def sparql(query: str) -> list[dict]:
    data = urllib.parse.urlencode({"query": query, "format": "json"}).encode()
    req = urllib.request.Request(
        ENDPOINT, data=data, headers={"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"}
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.loads(resp.read().decode("utf-8"))["results"]["bindings"]
        except Exception as exc:  # network hiccups and rate limits: back off and retry
            if attempt == 3:
                raise
            print(f"  retrying after {exc}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    return []


def _values(names: list[str]) -> str:
    def lit(s: str, lang: str) -> str:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + f'"@{lang}'

    return " ".join(lit(n, lang) for n in names for lang in ("en", "mul"))


def people(names: list[str]) -> dict[str, list[dict]]:
    found: dict[str, list[dict]] = {}
    for i in range(0, len(names), 80):
        batch = names[i : i + 80]
        query = f"""
        SELECT ?name ?item ?desc (COUNT(?f) AS ?footballer) WHERE {{
          VALUES ?name {{ {_values(batch)} }}
          ?item rdfs:label ?name ; wdt:P31 wd:Q5 .
          OPTIONAL {{ ?item wdt:P106 ?f . FILTER(?f = wd:{FOOTBALLER}) }}
          OPTIONAL {{ ?item schema:description ?desc . FILTER(lang(?desc) = "en") }}
        }} GROUP BY ?name ?item ?desc"""
        for row in sparql(query):
            name = row["name"]["value"]
            found.setdefault(name, []).append(
                dict(
                    item=row["item"]["value"].rsplit("/", 1)[-1],
                    description=row.get("desc", {}).get("value"),
                    footballer=int(row["footballer"]["value"]) > 0,
                )
            )
        time.sleep(1.0)
    return found


def anything(names: list[str]) -> dict[str, list[dict]]:
    found: dict[str, list[dict]] = {}
    for i in range(0, len(names), 60):
        batch = names[i : i + 60]
        query = f"""
        SELECT ?name ?item ?desc WHERE {{
          VALUES ?name {{ {_values(batch)} }}
          ?item rdfs:label ?name .
          OPTIONAL {{ ?item schema:description ?desc . FILTER(lang(?desc) = "en") }}
        }}"""
        for row in sparql(query):
            name = row["name"]["value"]
            found.setdefault(name, []).append(
                dict(item=row["item"]["value"].rsplit("/", 1)[-1], description=row.get("desc", {}).get("value"))
            )
        time.sleep(1.0)
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    league = build_league(args.seed)
    person_names = sorted({n for kind, n in league.all_names() if kind != "club"})
    clubs = [c.spec for c in league.clubs]
    club_names = sorted({c.name for c in clubs} | {c.short_name for c in clubs})
    print(f"checking {len(person_names)} people and {len(club_names)} club and place names against Wikidata")
    hits_people = people(person_names)
    hits_clubs = anything(club_names)
    results: dict[str, dict] = {}
    for name in person_names:
        matches = hits_people.get(name, [])
        status = "collision" if any(m["footballer"] for m in matches) else ("caution" if matches else "clear")
        results[name] = dict(kind="person", status=status, matches=matches)
    for name in club_names:
        matches = hits_clubs.get(name, [])
        football = any("football" in (m["description"] or "").lower() for m in matches)
        status = "collision" if football else ("caution" if matches else "clear")
        results[name] = dict(kind="club_or_place", status=status, matches=matches)
    record = dict(
        checked=datetime.now(UTC).isoformat(timespec="seconds"),
        source="Wikidata Query Service, exact English and multilingual labels",
        league_seed=args.seed,
        counts={s: sum(1 for r in results.values() if r["status"] == s) for s in ("clear", "caution", "collision")},
        names=results,
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT}: {record['counts']}")
    for name, r in results.items():
        if r["status"] != "clear":
            print(f"  {r['status']:9s} {name}: " + "; ".join(f"{m['item']} {m['description']}" for m in r["matches"]))
    return 1 if record["counts"]["collision"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
