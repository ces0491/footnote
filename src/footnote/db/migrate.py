"""Schema migrations and database roles, applied by the processor when it starts.

The processor's identity is the server's Entra administrator and owns the schema. It applies the
numbered SQL files under migrations/ in order, each once, under an advisory lock so two replicas
can't race. It then makes sure the web app's and the agents service's identities exist as database
roles with the privileges in WEB_GRANTS and AGENT_GRANTS, and nothing more.
"""

from __future__ import annotations

import logging
from importlib.resources import files

import psycopg
from azure.core.credentials_async import AsyncTokenCredential
from psycopg import sql

from footnote.db.connect import TOKEN_SCOPE, Pool, conninfo

log = logging.getLogger(__name__)

MIGRATIONS = files("footnote.db") / "migrations"
_LOCK_KEY = 7_340_001  # fixed key for pg_advisory_xact_lock while migrating

# What the web app's identity may do, table by table. It serves viewers and writes nothing. It may not
# read who started a run: the producer's desk checks that, in the agents service.
WEB_GRANTS: dict[str, str] = {
    "matches": "select",
    "runs": "select (run_id, match_id, descriptor, status, created_at, ended_at, insight_rev, producer)",
    "feed_events": "select",
    "run_state": "select",
    "insights": "select",
    "insight_versions": "select",
    "insight_cards": "select",
    "agent_runs": "select",
    "tracking_chunks": "select",
}

# What the agents service's identity may do. It reads the match and writes only its own work and the
# producer's: agent and producer versions, an insight's agent and status columns, the run's insight
# revision and how its graphics are approved, its run log and its cache.
AGENT_GRANTS: dict[str, str] = {
    "matches": "select",
    "runs": "select, update (insight_rev, producer)",
    "feed_events": "select",
    "insights": (
        "select, update (agent_state, agent_note, agent_attempts, agent_lease, redraft, queued_at, version,"
        " status, status_by, status_at, updated_at)"
    ),
    "insight_versions": "select, insert",
    "insight_cards": "select",
    "agent_runs": "select, insert, update",
    "agent_cache": "select, insert",
}


async def migrate(pool: Pool) -> list[str]:
    """Apply pending migrations; returns the versions applied."""
    applied: list[str] = []
    async with pool.connection() as conn, conn.transaction():
        await conn.execute("select pg_advisory_xact_lock(%s)", (_LOCK_KEY,))
        await conn.execute(
            "create table if not exists schema_migrations"
            " (version text primary key, applied_at timestamptz not null default now())"
        )
        rows = await (await conn.execute("select version from schema_migrations")).fetchall()
        done = {row["version"] for row in rows}
        for script in sorted((p for p in MIGRATIONS.iterdir() if p.name.endswith(".sql")), key=lambda p: p.name):
            version = script.name.removesuffix(".sql")
            if version in done:
                continue
            await conn.execute(script.read_bytes())
            await conn.execute("insert into schema_migrations (version) values (%s)", (version,))
            applied.append(version)
    return applied


async def ensure_role(
    credential: AsyncTokenCredential, pool: Pool, role: str, object_id: str, grants: dict[str, str]
) -> None:
    """Create a service's Entra role if it's missing, then give it `grants` and nothing more on those
    tables: what an earlier version granted is revoked first, in the same transaction."""
    token = await credential.get_token(TOKEN_SCOPE)
    # Entra principals are created from the server's `postgres` database.
    async with await psycopg.AsyncConnection.connect(
        conninfo("postgres"), password=token.token, autocommit=True
    ) as admin:
        exists = await (await admin.execute("select 1 from pg_roles where rolname = %s", (role,))).fetchone()
        if exists is None:
            await admin.execute(
                "select * from pgaadauth_create_principal_with_oid(%s, %s, 'service', false, false)", (role, object_id)
            )
            log.info("created database role %s", role)
    async with pool.connection() as conn, conn.transaction():
        await conn.execute(sql.SQL("grant usage on schema public to {}").format(sql.Identifier(role)))
        for table, privileges in grants.items():
            await conn.execute(
                sql.SQL("revoke all on table {} from {}").format(sql.Identifier(table), sql.Identifier(role))
            )
            await conn.execute(
                sql.SQL("grant {} on table {} to {}").format(
                    sql.SQL(privileges), sql.Identifier(table), sql.Identifier(role)
                )
            )
