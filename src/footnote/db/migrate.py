"""Schema migrations and database roles, applied by the processor when it starts.

The processor's identity is the server's Entra administrator and owns the schema. It applies the
numbered SQL files under migrations/ in order, each once, under an advisory lock so two replicas
can't race. It then makes sure the web app's identity exists as a database role with the privileges
in WEB_GRANTS and nothing more.
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

# What the web app's identity may do, table by table. It serves viewers; it never writes the feed or
# a run's state.
WEB_GRANTS: dict[str, str] = {
    "matches": "select",
    "runs": "select",
    "feed_events": "select",
    "run_state": "select",
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


async def ensure_web_role(credential: AsyncTokenCredential, pool: Pool, role: str, object_id: str) -> None:
    """Create the web app's Entra role if it's missing, then grant it WEB_GRANTS."""
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
        for table, privileges in WEB_GRANTS.items():
            await conn.execute(
                sql.SQL("grant {} on table {} to {}").format(
                    sql.SQL(privileges), sql.Identifier(table), sql.Identifier(role)
                )
            )
