"""What crosses the service boundaries.

Event Hubs, replayer to processor. Each event's body is either one feed message, exactly as the
provider published it, or a control message from the replayer (`run_start`, `run_end`). Events are
partitioned by run ID, so a run's messages arrive in order. Application properties carry the
replay's bookkeeping:

    run_id        the replay the message belongs to
    kind          "feed" or "control"
    published_at  when the replayer sent it, epoch milliseconds
    backfill      true for the messages sent at once to bring a run up to its starting point

Web PubSub, processor to viewers, in the group `run-<run_id>`. JSON with a `type`:

    snapshot  the run descriptor and the full state view, once the backfill is processed
    event     one feed event (freeze frames and provider boilerplate dropped), whether it is a key
              event, the score, phase, clock and stats after it, and timing for latency measurement
    run_end   the replay finished, was stopped, expired, was evicted to make room, or failed (which
              includes a run the processor ended because its messages stopped arriving)

Every message carries `seq`, the feed sequence number the state reflects. A client that sees a gap
fetches the snapshot again.
"""

from __future__ import annotations

from typing import Literal

KIND_FEED = "feed"
KIND_CONTROL = "control"

PROP_RUN_ID = "run_id"
PROP_KIND = "kind"
PROP_PUBLISHED_AT = "published_at"
PROP_BACKFILL = "backfill"

RunEndReason = Literal["finished", "stopped", "expired", "evicted", "failed"]

# Fields viewers don't need on every event: provider boilerplate, the line-ups (sent once with the
# match metadata) and freeze frames (fetched with the evidence when a card needs them).
_CLIENT_DROP = frozenset({"feed_version", "match_id", "ts", "freeze_frame", "info"})


def group_name(run_id: str) -> str:
    return f"run-{run_id}"


def client_event(message: dict) -> dict:
    return {k: v for k, v in message.items() if k not in _CLIENT_DROP}
