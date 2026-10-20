import "server-only";

import { Pool } from "pg";

import { accessToken } from "./azure";
import { serverEnv } from "./env";

const TOKEN_SCOPE = "https://ossrdbms-aad.database.windows.net/.default";

let pool: Pool | undefined;

// Postgres accepts Entra tokens only. pg asks for the password on every new connection, so each one
// signs in with a current token. The web app's role can read matches, runs, their feed, state and
// insights, and write nothing (WEB_GRANTS in src/footnote/db/migrate.py).
export function db(): Pool {
  if (!pool) {
    const env = serverEnv();
    pool = new Pool({
      host: env.POSTGRES_HOST,
      database: env.POSTGRES_DATABASE,
      user: env.POSTGRES_USER,
      port: env.POSTGRES_PORT,
      password: () => accessToken(TOKEN_SCOPE),
      ssl: { rejectUnauthorized: true },
      max: 4,
      idleTimeoutMillis: 60_000,
      connectionTimeoutMillis: 10_000,
      application_name: "footnote-web",
    });
    pool.on("error", (error) => console.error("postgres pool error", error));
  }
  return pool;
}
