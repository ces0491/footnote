"""docs/evaluations.md, written from the recorded live run replayed through today's code."""

from __future__ import annotations

import statistics
from pathlib import Path

from footnote.evals.groundedness import NAME as GROUNDED
from footnote.evals.judges import EVALUATORS
from footnote.evals.run import Result

# gpt-5-mini Global Standard list prices, US dollars per token, as docs/architecture.md's cost table
# gives them (Azure Retail Prices API, 20 October 2026).
INPUT_PRICE = 0.25 / 1_000_000
OUTPUT_PRICE = 2.00 / 1_000_000

_INTRO = """\
# Agent evaluations

How well the agents word the showcase match's cards. Each case is a job the agents service gets in
a replay: every card the agents draft in a replay from kick-off, the 81st-minute goal again after
its correction, and the catch-up that opens a replay from 23', 31', 60' and 81'. The writer runs as
it does in the service: the same instructions, the match tools over MCP, and code's checks with one
revision ([insights.md](insights.md#the-agents)).

The checks refuse a draft that types a figure or names someone the facts don't. The evaluators
judge some of what the checks can't. Four are rough tests in code, described in the table below
(`src/footnote/evals/judges.py`). None of them can tell whose a claim is, so a card that gives the
right words to the wrong player or moment passes all four. The fifth is Azure AI Evaluation's
groundedness evaluator, on the same Foundry deployment (`src/footnote/evals/groundedness.py`). It
catches a sentence that contradicts the facts, such as "the only shot of the match" when the match
has had three, but it is lenient. In earlier recordings, from 21 October, whose cards aren't in the
tables below, it scored 4 or 5 a card that gave Varlan's pass the minute of the VAR decision on it,
one that wrote of a handball VAR had found no offence in, and one that said a counter started with
the pass that ended it. Reading the cards stays part of a review.

CI (`tests/test_evals.py`) replays the recorded drafts through the current checks and evaluators on
each push to main and each pull request. It fails unless three cards in four pass every evaluation,
every draft accepted when recorded is still accepted, and this page is what the replay writes. A
change to the checks or the facts that a recorded draft no longer passes fails the build. The
recording keeps the version and a fingerprint of the code of each part of what the writers are told
and shown (the instructions, the match tools with the templates' wording they return, the writer's
workflow), and the model's reasoning effort, so a change to any of them fails the build too until
the evaluations are recorded again. The judge's verdicts are replayed as recorded. When a reply
from the judge can't be read, the judge is asked again, up to three tries in all, before the card
counts as a fail.
"""


def _seconds(ms: list[int]) -> str:
    return f"{statistics.median(ms) / 1000:.1f} s" if ms else "none"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def write_report(path: Path, results: list[Result], recording: dict) -> None:
    """The report on a recording, from its replay through today's checks and code evaluators."""
    accepted = [r for r in results if r.outcome == "accepted"]
    first = sum(r.attempts == 1 for r in accepted)
    verdicts = [v for r in accepted for v in r.verdicts]
    latencies = [r.latency_ms for r in results if r.latency_ms]
    cost = sum(r.input_tokens * INPUT_PRICE + r.output_tokens * OUTPUT_PRICE for r in results)
    v = recording["versions"]
    run = (
        f"{recording['recorded_at'][:10]}, against {recording['model']} (reasoning effort"
        f" {recording['reasoning_effort']}; prompt {v['prompt']}, tools {v['tools']}, writer {v['writer']})"
    )
    made = (
        f"The cards were drafted and judged by `uv run --group evals python -m footnote.evals live --record` on {run}. "
        "This report replays them through the current checks and code evaluators: "
        "`uv run python -m footnote.evals replay --report`."
    )
    lines = [
        _INTRO,
        made,
        "",
        "## Results",
        "",
        "| | |",
        "| --- | --- |",
        f"| Cases | {len(results)} |",
        f"| Accepted at the first attempt | {first} |",
        f"| Accepted after a revision | {len(accepted) - first} |",
        f"| Rejected, late or failed: the template stands | {len(results) - len(accepted)} |",
        f"| Accepted with every evaluation passed | {sum(r.passed for r in results)} |",
        f"| Evaluations passed | {sum(x.passed for x in verdicts)} of {len(verdicts)} |",
        f"| Time to a draft | median {_seconds(latencies)}, slowest {max(latencies, default=0) / 1000:.1f} s |",
        f"| Tokens per card | median {statistics.median([r.input_tokens for r in results]):.0f} in, "
        f"{statistics.median([r.output_tokens for r in results]):.0f} out |",
        f"| Cost of the drafts at list prices (the judge's calls aside) | US${cost:.3f} |",
        "",
        "## Evaluators",
        "",
        "| Evaluator | Passed | What it judges |",
        "| --- | --- | --- |",
    ]
    rows = [(judge.__name__.replace("_", " "), " ".join((judge.__doc__ or "").split())) for judge in EVALUATORS]
    rows.append((GROUNDED, "A model reads the card against its writer's facts and scores it 1 to 5; it passes at 3."))
    for name, doc in rows:
        mine = [x for x in verdicts if x.evaluator == name]
        lines.append(f"| {name} | {sum(x.passed for x in mine)} of {len(mine)} | {doc} |")
    lines += [
        "",
        "## Cases",
        "",
        "| Case | Outcome | Headline and casual line | Evaluations |",
        "| --- | --- | --- | --- |",
    ]
    for r in results:
        outcome = f"{r.outcome}, {r.attempts} attempt{'s' if r.attempts != 1 else ''}, {r.latency_ms / 1000:.1f} s"
        if r.card is None:
            card = _cell("; ".join(r.problems) or "no draft")
        else:
            card = _cell(f"**{r.card.headline}** {r.card.casual}")
        failed = [f"{x.evaluator}: {x.note}" for x in r.verdicts if not x.passed]
        verdict = _cell("; ".join(failed)) if failed else ("all passed" if r.verdicts else "none")
        lines.append(f"| `{r.case.key}` | {outcome} | {card} | {verdict} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
