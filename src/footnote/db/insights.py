"""Insight rows shared by the processor and the agents: revisions, and the cards viewers get.

Both services change a run's insights. The processor finds them and writes the templates' versions;
the agents write theirs. Each change bumps the run's insight revision in the same transaction
(`next_rev`), so the revisions a run's viewers see have no gaps unless a push went missing. What a
viewer gets for an insight is its row of the `insight_cards` view (migration 0002), read as JSON by
`cards` here and by the web app's snapshot route alike.
"""

from __future__ import annotations

from psycopg import AsyncConnection
from psycopg.rows import DictRow

# The Postgres channel the processor notifies when an insight wants an agent's draft.
AGENT_CHANNEL = "footnote_agents"

Connection = AsyncConnection[DictRow]


async def next_rev(conn: Connection, run_id: str, count: int = 1) -> int:
    """Take the run's next `count` insight revisions and return the last; the row lock it takes
    orders concurrent writers until their transactions end."""
    cur = await conn.execute(
        "update runs set insight_rev = insight_rev + %s where run_id = %s returning insight_rev", (count, run_id)
    )
    row = await cur.fetchone()
    if row is None:
        raise LookupError(f"run {run_id} is not on record")
    return int(row["insight_rev"])


async def cards(conn: Connection, run_id: str, insight_ids: list[str]) -> list[dict]:
    """The cards viewers get for these insights, as JSON."""
    cur = await conn.execute(
        "select to_jsonb(c) - 'run_id' as doc from insight_cards c where c.run_id = %s and c.insight_id = any(%s)",
        (run_id, insight_ids),
    )
    return [row["doc"] for row in await cur.fetchall()]


def insight_push(run_id: str, rev: int, card: dict) -> dict:
    """The Web PubSub message for a changed insight (live/contract.py)."""
    return {"type": "insight", "run_id": run_id, "rev": rev, "insight": card}
