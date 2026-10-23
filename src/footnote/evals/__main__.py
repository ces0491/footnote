"""Evaluate the agents on the showcase match: python -m footnote.evals.

    live [--only KEY ...] [--record] [--report] [--deadline S] [--effort E] [--no-judge]
        Draft every case with the Foundry model (FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL, signed
        in through the Azure CLI), as the agents service does, and have the model judge each card's
        groundedness (needs `uv run --group evals`). --record keeps the model's output in
        data/evals/drafts.json for replaying; --report, with --record, then writes
        docs/evaluations.md from a replay of the recording, as replay --report does. --only with
        --record updates those cases in a recording made with today's versions, and refuses an
        older one: its other cases were drafted with something else. --effort tries another
        reasoning effort than the service's; CI refuses a recording made with it until the service
        uses it too.
    replay [--report]
        Run the recorded output through today's writer workflow, checks and evaluators, as CI does,
        and pass as CI does; --report writes docs/evaluations.md from the replay, which CI compares
        with the committed page.

A live run drafts a card for each case and judges it: a few US cents at gpt-5-mini's list prices.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from footnote import cloud
from footnote.agents.versions import VERSIONS
from footnote.agents.worker import Settings
from footnote.evals.cases import cases
from footnote.evals.report import write_report
from footnote.evals.run import PASSING_SHARE, Result, judge_groundedness, passing, replay, run, stale
from footnote.live.analysis import Analysis
from footnote.live.match import load_match

ROOT = Path(__file__).resolve().parents[3]
RECORDING = ROOT / "data" / "evals" / "drafts.json"
REPORT = ROOT / "docs" / "evaluations.md"


def show(results: list[Result]) -> None:
    for r in results:
        print(
            f"{r.case.key}: {r.outcome}, {r.attempts} attempt(s), {r.latency_ms} ms, "
            f"{r.input_tokens} in / {r.output_tokens} out"
        )
        if r.card is not None:
            print(f"    {r.card.headline}\n    casual: {r.card.casual}\n    analyst: {r.card.analyst}")
        if r.groundedness is not None:
            print(f"    grounded: {r.groundedness['score']} ({'pass' if r.groundedness['passed'] else 'fail'})")
        for p in r.problems:
            print(f"    problem: {p}")
        for v in r.verdicts:
            if not v.passed:
                print(f"    FAILED {v.evaluator}: {v.note}")
    passed = sum(r.passed for r in results)
    print(f"{passed} of {len(results)} cases accepted with every evaluation passed")


async def live(only: list[str], record: bool, report: bool, deadline: float, effort: str, judge: bool) -> int:
    from agent_framework_foundry import FoundryChatClient

    if record and only and RECORDING.exists():
        older = stale(json.loads(RECORDING.read_text(encoding="utf-8")))
        if older:
            print(f"the recording predates {'; '.join(older)}: record every case, without --only")
            return 2
    match = load_match()
    analysis = Analysis.load(match)
    picked = [c for c in cases(match, analysis) if not only or c.key in only]
    model = cloud.require("FOUNDRY_MODEL")
    endpoint = cloud.require("FOUNDRY_PROJECT_ENDPOINT")
    credential = cloud.credential()
    client = FoundryChatClient(project_endpoint=endpoint, model=model, credential=credential)
    settings = Settings(model=model, reasoning_effort=effort)
    try:
        results = await run(match, analysis, picked, lambda c: client, settings.options, deadline_seconds=deadline)
    finally:
        await credential.close()
    if judge:
        from footnote.evals.groundedness import Groundedness

        await judge_groundedness(results, Groundedness(endpoint, model))
    # Kept before anything is printed: the model's output is paid for.
    if record:
        recording = {
            "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "model": model,
            "reasoning_effort": settings.reasoning_effort,
            "versions": VERSIONS,
            "cases": {r.case.key: r.recorded() for r in results},
        }
        if only and RECORDING.exists():
            # A partial run updates its own cases and keeps the rest.
            kept = json.loads(RECORDING.read_text(encoding="utf-8"))
            recording["cases"] = kept["cases"] | recording["cases"]
        RECORDING.parent.mkdir(parents=True, exist_ok=True)
        RECORDING.write_text(json.dumps(recording, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    if report:
        # The page is the recording replayed through today's code, as CI checks it: with --only, the
        # recording holds the other cases too.
        recording = json.loads(RECORDING.read_text(encoding="utf-8"))
        write_report(REPORT, await replay(match, analysis, cases(match, analysis), recording), recording)
    show(results)
    if record:
        print(f"recorded in {RECORDING.relative_to(ROOT)}")
    if report:
        print(f"report in {REPORT.relative_to(ROOT)}")
    return 0 if all(r.passed for r in results) else 1


async def replayed(report: bool) -> int:
    match = load_match()
    analysis = Analysis.load(match)
    recording = json.loads(RECORDING.read_text(encoding="utf-8"))
    for change in stale(recording):
        print(f"the recording predates {change}: record it again with `python -m footnote.evals live --record`")
    results = await replay(match, analysis, cases(match, analysis), recording)
    show(results)
    if report:
        write_report(REPORT, results, recording)
        print(f"report in {REPORT.relative_to(ROOT)}")
    # As CI judges it (tests/test_evals.py): no case the model had accepted is refused today, and
    # the share passing every evaluation clears the bar.
    refused = [
        r.case.key
        for r in results
        if recording["cases"].get(r.case.key, {}).get("outcome") == "accepted" and r.outcome != "accepted"
    ]
    for key in refused:
        print(f"{key}: accepted when recorded, refused by today's checks")
    share = passing(results)
    print(f"{share:.0%} pass every evaluation; CI needs {PASSING_SHARE:.0%}")
    return 0 if share >= PASSING_SHARE and not refused and not stale(recording) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    live_parser = commands.add_parser("live", help="draft every case with the Foundry model")
    live_parser.add_argument("--only", nargs="*", default=[], help="case keys, such as ft/v1 or catchup@60")
    live_parser.add_argument("--record", action="store_true", help="keep the model's output for replaying")
    live_parser.add_argument(
        "--report", action="store_true", help="with --record, write docs/evaluations.md from the recording"
    )
    live_parser.add_argument(
        "--deadline", type=float, default=Settings.deadline_seconds, help="seconds per case, the service's by default"
    )
    live_parser.add_argument(
        "--effort",
        choices=("low", "medium", "high"),
        default=Settings.reasoning_effort,
        help="the writers' reasoning effort, the service's by default",
    )
    live_parser.add_argument(
        "--no-judge", action="store_true", help="skip the model-judged groundedness (no `evals` group needed)"
    )
    replay_parser = commands.add_parser("replay", help="evaluate the recorded output with today's code")
    replay_parser.add_argument("--report", action="store_true", help="write docs/evaluations.md from the replay")
    args = parser.parse_args()
    if args.command == "live" and args.report and not args.record:
        parser.error("live --report needs --record: the report is written from the recording")
    # A card can hold a character the console's code page lacks (a non-breaking hyphen on Windows).
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(errors="replace")
    # Before the match tools' server is built, which would otherwise log every request.
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    if args.command == "live":
        return asyncio.run(live(args.only, args.record, args.report, args.deadline, args.effort, not args.no_judge))
    return asyncio.run(replayed(args.report))


if __name__ == "__main__":
    sys.exit(main())
