"""The overlay contract: one item per insight, as viewers and graphics systems get it.

An item is a row of the `insight_cards` view (migrations 0002 and 0004), pushed to a run's viewers
whenever it changes and served in the run's snapshot. docs/overlay.md says what each field is for
and how a client times, places and retires an item; `docs/overlay.schema.json` is the JSON Schema
of `OverlayItem`, written by `python -m footnote.live.overlay`.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MatchTime(_Strict):
    """A moment in the match: `t` seconds into `period`, and the minute a broadcast shows for it."""

    period: int = Field(ge=1, le=2)
    t: float = Field(ge=0, description="Seconds since the period kicked off")
    minute: int | None = Field(default=None, description="As a broadcast shows it: the 23rd minute runs from 22:00")
    added_minute: int | None = Field(default=None, description="The minute of added time, or null in normal time")


class Flag(_Strict):
    """Set when VAR or the provider's correction undid what the item cites."""

    reason: str
    event_id: str = Field(description="The VAR decision or the correction")
    version: int
    seq: int = Field(description="The feed message that flagged it")


class Card(_Strict):
    """The item's wording, with code's figures filled in."""

    headline: str = Field(description="For a lower third: 60 characters at most")
    casual: str = Field(
        description="For a casual fan: why it matters, in one or two sentences (up to three in a recap)"
    )
    analyst: str = Field(description="For an analyst: the numbers behind it, in one to three sentences")
    plain: str = Field(description="The headline and the casual line as one text, for screen readers")
    evidence: list[str] = Field(description="Event IDs the wording rests on: those cited, then those behind its facts")
    facts: list[str] = Field(description="The fact keys the wording used")


class Translation(_Strict):
    """The item's wording in another language: Azure AI Translator's, checked by code to keep every
    figure and name of the English."""

    headline: str
    casual: str
    analyst: str


class Provenance(_Strict):
    """Where the wording came from and what was checked."""

    source: Literal["template", "agent", "producer"]
    template: str | None = Field(default=None, description="The template that worded it")
    agent_run_id: str | None = Field(default=None, description="The agent run that wrote it")
    model: str | None = None
    prompt: str | None = Field(default=None, description="The version of the agent's instructions")
    attempts: int | None = None
    tools: list[str] | None = Field(default=None, description="The match tools the agent called")
    latency_ms: int | None = None
    checks: Literal["passed"] | None = Field(default=None, description="Every version a viewer sees passed the checks")
    cached: bool | None = Field(default=None, description="Written for an earlier replay and checked again")
    edited_from: int | None = Field(default=None, description="The version the producer edited")


class OverlayItem(_Strict):
    """One insight as it stands: what it is, when to show it, where, for how long, and its record."""

    # Identity and lineage
    match_id: str
    insight_id: str = Field(description="Stable for the insight: a later state of it replaces the earlier")
    corrects: str | None = Field(description="The item a correction is about")
    evidence: list[str] = Field(description="The events the moment rests on")
    flag: Flag | None
    # What it is, and its rank
    kind: Literal["moment", "rule_call", "segment", "stat", "player_tag", "recap", "correction"]
    topic: str = Field(description="What happened, and the graphics template that shows it")
    rank: float = Field(
        ge=0, le=1, description="A base for the topic, raised by the match state and the moment's figures"
    )
    reason: str = Field(description="Why it ranks where it does")
    live: bool = Field(description="False for a moment the replay's start passed: history, for catch-up only")
    # Timing
    seq: int = Field(description="The feed message its facts are as of")
    at: MatchTime = Field(description="When it happened")
    until: MatchTime = Field(description="When it leaves the producer's shortlist")
    shown_seq: int = Field(description="The feed message behind its current state")
    shown_at: MatchTime = Field(description="That message's match time: show the item once playback reaches it")
    ts: str = Field(description="That message's timestamp from the provider")
    hold: Literal["stoppage"] | None = Field(description="Wait for the next stoppage after shown_at")
    duration: float | None = Field(description="Seconds of match time on screen; null for a side-panel card")
    # Presentation
    placement: Literal["lower_third", "side_panel", "full_card"]
    motion: Literal["still", "animated"] = Field(description="Whether it may animate; calm mode keeps it still")
    # Content
    version: int = Field(description="The version of the wording viewers see")
    source: Literal["template", "agent", "producer"]
    card: Card
    translations: dict[Literal["es", "fr"], Translation] = Field(
        default_factory=dict,
        description="The wording in Spanish and French, once translated and checked; a language not here shows the English",
    )
    fields: dict[str, str] = Field(description="Each fact's text by key, for graphics systems filling a template")
    provenance: Provenance
    # Status
    status: Literal["drafted", "approved", "withdrawn", "killed"] = Field(description="Only an approved item airs")
    status_by: Literal["auto", "producer", "correction"] | None = Field(
        description="Who set the status: automatic approval, the producer, or a correction that needs approval again"
    )
    status_at: datetime | None
    agent_state: Literal["off", "pending", "drafting", "done", "fallback"]
    agent_note: str | None = Field(description="Why the template stands, when it does")
    created_at: datetime
    updated_at: datetime


def schema() -> dict:
    return OverlayItem.model_json_schema()


if __name__ == "__main__":
    json.dump(schema(), sys.stdout, indent=2)
    sys.stdout.write("\n")
