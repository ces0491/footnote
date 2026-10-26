"""Groundedness, judged by a model: whether what a card says is supported by the facts its writer
was given.

The code evaluators (judges.py) see claims they have words for. A sentence can still say something
the facts don't, such as "the only shot of the match" from one spell's single shot when the match has
had three. Azure AI Evaluation's groundedness evaluator reads the card against the facts and scores it
from 1 to 5, passing at 3 or more, with its reason. It runs on the same Foundry deployment as the
writers, signed in through the Azure CLI, and only in a live evaluation: the verdicts are recorded
with the drafts, and a replay reports them as recorded.

Needs the `evals` dependency group: `uv run --group evals python -m footnote.evals live`.
"""

from __future__ import annotations

import asyncio
import os
from urllib.parse import urlparse

from footnote.evals.judges import Verdict
from footnote.insights.draft import Card
from footnote.insights.facts import Facts

API_VERSION = "2025-04-01-preview"
NAME = "grounded"


def openai_endpoint(project_endpoint: str) -> str:
    """The Foundry account's OpenAI endpoint, which the evaluator calls. Both share the account's
    custom subdomain (infra/resources.bicep); FOUNDRY_OPENAI_ENDPOINT overrides it."""
    override = os.environ.get("FOUNDRY_OPENAI_ENDPOINT")
    if override:
        return override
    host = urlparse(project_endpoint).hostname or ""
    return f"https://{host.split('.')[0]}.openai.azure.com/"


def context_of(facts: Facts, reason: str) -> str:
    """What the card may rest on, as the judge reads it: why the moment was picked, then each fact."""
    lines = [f"Why the moment was picked: {reason}"]
    lines += [f"{fact.about}: {fact.display}" for fact in facts.values()]
    return "\n".join(lines)


class Groundedness:
    def __init__(self, project_endpoint: str, deployment: str) -> None:
        from azure.ai.evaluation import AzureOpenAIModelConfiguration, GroundednessEvaluator
        from azure.identity import AzureCliCredential

        config = AzureOpenAIModelConfiguration(
            azure_endpoint=openai_endpoint(project_endpoint), azure_deployment=deployment, api_version=API_VERSION
        )
        self.evaluator = GroundednessEvaluator(config, credential=AzureCliCredential(), is_reasoning_model=True)

    def _judge(self, card: Card, facts: Facts, reason: str) -> dict:
        response = f"{card.headline}. {card.casual} {card.analyst}"
        query = "A card for live football graphics: a headline, a line for casual fans and one for analysts."
        return dict(self.evaluator(query=query, response=response, context=context_of(facts, reason)))

    async def judge(self, card: Card, facts: Facts, reason: str) -> dict:
        """The evaluator's score (1 to 5), whether it passed and its reason."""
        result = await asyncio.to_thread(self._judge, card, facts, reason)
        return {
            "score": result.get("groundedness"),
            "passed": result.get("groundedness_result") == "pass",
            "reason": str(result.get("groundedness_reason", "")),
        }


def verdict(recorded: dict | None) -> Verdict | None:
    """The recorded judgement as a verdict beside the code evaluators' own. A fail keeps the whole
    reason, less the evaluator's stock opening: the reason lists what the card got right before the
    fault it found."""
    if not recorded:
        return None
    if recorded["passed"]:
        return Verdict(NAME, True, "")
    reason = str(recorded["reason"]).removeprefix("Let's think step by step:").strip()
    score = recorded["score"]  # None when the judge's replies couldn't be read
    return Verdict(NAME, False, reason if score is None else f"scored {score:g} of 5: {reason}")
