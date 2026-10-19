"""Connection pools that sign in to Azure Database for PostgreSQL with Microsoft Entra ID.

The server accepts Entra tokens only; password authentication is off. Each new connection asks the
credential for a token (the credential caches it until it nears expiry), and the pool retires
connections well inside a token's lifetime. The server's certificate is verified against certifi's
CA bundle, which behaves the same in the container and on a developer's Windows machine.
"""

from __future__ import annotations

import os
from typing import Any

import certifi
from azure.core.credentials_async import AsyncTokenCredential
from psycopg import AsyncConnection
from psycopg.conninfo import make_conninfo
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from footnote.cloud import require

TOKEN_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"

Pool = AsyncConnectionPool[AsyncConnection[DictRow]]


def conninfo(database: str | None = None) -> str:
    """From POSTGRES_HOST, POSTGRES_DATABASE and POSTGRES_USER (the Entra role, named after the identity)."""
    return make_conninfo(
        host=require("POSTGRES_HOST"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=database or require("POSTGRES_DATABASE"),
        user=require("POSTGRES_USER"),
        sslmode="verify-full",
        sslrootcert=certifi.where(),
        application_name=os.environ.get("CONTAINER_APP_NAME", "footnote"),
    )


def entra_pool(credential: AsyncTokenCredential, *, database: str | None = None, max_size: int = 4) -> Pool:
    """A pool whose connections return rows as dicts."""

    async def password() -> dict[str, Any]:
        token = await credential.get_token(TOKEN_SCOPE)
        return {"password": token.token, "row_factory": dict_row}

    return AsyncConnectionPool(
        conninfo(database),
        connection_class=AsyncConnection[DictRow],
        kwargs=password,
        min_size=1,
        max_size=max_size,
        max_lifetime=30 * 60.0,
        open=False,
    )
