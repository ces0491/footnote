"""Evaluate the agents on the showcase match: python -m footnote.evals.

    live [--only KEY ...] [--record] [--report] [--deadline S] [--no-judge]
        Draft every case with the Foundry model (FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL, signed
        in through the Azure CLI), as the agents service does, and have the model judge each card's
        groundedness (needs `uv run --group evals`). --record keeps the model's output in
        data/evals/drafts.json for replaying; --report writes docs/evaluations.md.
    replay [--report]
        Run the recorded output through today's writer workflow, checks and evaluators, as CI does;
        --report writes docs/evaluations.md from the replay.

A live run of every case drafts about twenty cards and judges each: a few US cents at gpt-5-mini's
list prices.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from footnote import cloud
from footnote.agents.worker import Settings
from footnote.evals.cases import cases
from footnote.evals.report import write_report
from footnote.evals.run import VERSIONS, Result, judge_groundedness, replay, run, stale
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


async def live(only: list[str], record: bool, report: bool, deadline: float, judge: bool) -> int:
    from agent_framework_foundry import FoundryChatClient

    match = load_match()
    analysis = Analysis.load(match)
    picked = [c for c in cases(match, analysis) if not only or c.key in only]
    model = cloud.require("FOUNDRY_MODEL")
    endpoint = cloud.require("FOUNDRY_PROJECT_ENDPOINT")
    credential = cloud.credential()
    client = FoundryChatClient(project_endpoint=endpoint, model=model, credential=credential)
    settings = Settings(model=model)
    try:
        results = await run(match, analysis, picked, lambda c: client, settings.options, deadline_seconds=deadline)
    finally:
        await credential.close()
    if judge:
        from footnote.evals.groundedness import Groundedness

        await judge_groundedness(results, Groundedness(endpoint, model))
    show(results)
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
        print(f"recorded in {RECORDING.relative_to(ROOT)}")
    if report:
        write_report(REPORT, results, json.loads(RECORDING.read_text(encoding="utf-8")))
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
        write_report(REPORT, results, recording, replayed=True)
        print(f"report in {REPORT.relative_to(ROOT)}")
    return 0 if all(r.passed for r in results) and not stale(recording) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    live_parser = commands.add_parser("live", help="draft every case with the Foundry model")
    live_parser.add_argument("--only", nargs="*", default=[], help="case keys, such as ft/v1 or catchup@60")
    live_parser.add_argument("--record", action="store_true", help="keep the model's output for replaying")
    live_parser.add_argument("--report", action="store_true", help="write docs/evaluations.md")
    live_parser.add_argument(
        "--deadline", type=float, default=Settings.deadline_seconds, help="seconds per case, the service's by default"
    )
    live_parser.add_argument(
        "--no-judge", action="store_true", help="skip the model-judged groundedness (no `evals` group needed)"
    )
    replay_parser = commands.add_parser("replay", help="evaluate the recorded output with today's code")
    replay_parser.add_argument("--report", action="store_true", help="write docs/evaluations.md from the replay")
    args = parser.parse_args()
    # Before the match tools' server is built, which would otherwise log every request.
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    if args.command == "live":
        return asyncio.run(live(args.only, args.record, args.report, args.deadline, not args.no_judge))
    return asyncio.run(replayed(args.report))


if __name__ == "__main__":
    sys.exit(main())
