"""What crosses the service boundaries.

Event Hubs, replayer to processor. Each event's body is either one feed message, exactly as the
provider published it, or a control message from the replayer: `run_start` with the run descriptor,
the anonymous ID of the viewer who started it (`viewer`, kept out of the descriptor every viewer can
read) and how its graphics are approved (`producer`, "auto" or "manual"); or `run_end`. Events are
partitioned by run ID, so a run's messages arrive in order. Application properties carry the
replay's bookkeeping:

    run_id        the replay the message belongs to
    kind          "feed" or "control"
    published_at  when the replayer sent it, epoch milliseconds
    backfill      true for the messages sent at once to bring a run up to its starting point

Web PubSub, processor to viewers, in the group `run-<run_id>`. JSON with a `type`:

    snapshot  the run descriptor and the full state view, once the backfill is processed: with the
              models (live/analysis.py), also the match-state timeline, every player's line and
              the tags so far
    event     one feed event (freeze frames and provider boilerplate dropped), whether it is a key
              event, the score, phase, clock, stats and match state after it, `replay` (the replay
              second at which the provider published it), `stoppage` (whether play is stopped
              after it) and timing for latency measurement; with the models, also a pass's
              `difficulty`, the `player` line of the player on the event, and any `tags` that fell
              due with it
    insight   one insight as it now stands (its row of the `insight_cards` view: one item of the
              overlay contract, docs/overlay.md) and `rev`, the run's insight revision the change
              made; the processor and the agents service both send them (footnote.db.insights)
    run_end   the replay finished, was stopped (by its viewer, or by their next replay), expired,
              was evicted to make room, or failed (which includes a run the processor ended because
              its messages stopped arriving, or over a message it couldn't fold)

A snapshot and each event carry `seq`, the feed sequence number the state reflects, and an insight
carries `rev`. A client that sees a gap in either fetches the snapshot again. Messages go out as
compact JSON text (`wire`), so the bytes Web PubSub bills in 2 KB units are the bytes the tests
measure.

The processor also stores each event push with its feed row, and the snapshot with the backfill's
last row, so a viewer whose stream runs behind live can fetch what it missed and see the match as
of its own playback (frontend/src/lib/live/playback.ts).
"""

from __future__ import annotations

import json
from typing import Literal

KIND_FEED = "feed"
KIND_CONTROL = "control"

PROP_RUN_ID = "run_id"
PROP_KIND = "kind"
PROP_PUBLISHED_AT = "published_at"
PROP_BACKFILL = "backfill"

RunEndReason = Literal["finished", "stopped", "expired", "evicted", "failed"]
ProducerMode = Literal["auto", "manual"]
PRODUCER_MODES: frozenset[str] = frozenset({"auto", "manual"})

# The anonymous ID a browser goes by: a random UUID (frontend/src/lib/live/viewer.ts).
VIEWER_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"

# Fields viewers don't need on every event: provider boilerplate, the line-ups (sent once with the
# match metadata) and freeze frames (fetched with the evidence when a card needs them).
_CLIENT_DROP = frozenset({"feed_version", "match_id", "ts", "freeze_frame", "info"})

# Events after which play is stopped: the pauses a fan's segment and stat cards wait for
# (docs/audience.md, P5). A foul played on with advantage isn't one.
STOPPAGE_TYPES = frozenset(
    {"ball_out", "foul", "offside", "goal", "card", "substitution", "injury", "var_check", "period_end", "match_end"}
)


def group_name(run_id: str) -> str:
    return f"run-{run_id}"


def client_event(message: dict) -> dict:
    return {k: v for k, v in message.items() if k not in _CLIENT_DROP}


def stoppage(message: dict) -> bool:
    """Whether play is stopped after this feed message."""
    return message["type"] in STOPPAGE_TYPES and not (message["type"] == "foul" and message.get("advantage"))


def wire(message: dict) -> str:
    """A pushed message as it travels: JSON without the spaces json.dumps puts after separators."""
    return json.dumps(message, separators=(",", ":"))
