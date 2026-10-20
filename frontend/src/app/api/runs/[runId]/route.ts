import type { NextRequest } from "next/server";

import { runIdPattern, type RunSnapshot } from "@/lib/live/contract";
import { db } from "@/lib/server/db";
import { runInProgress, stopRun } from "@/lib/server/replayer";

// The run's descriptor, its latest state view and the match metadata, from Postgres. The processor
// records a run within a second or two of its start; until then the answer is 202 for a run the
// replayer is playing, and 404 for one it doesn't know.
export async function GET(_request: NextRequest, ctx: RouteContext<"/api/runs/[runId]">) {
  const { runId } = await ctx.params;
  if (!runIdPattern.test(runId)) return Response.json({ error: "not a run ID" }, { status: 400 });
  const { rows } = await db().query(
    `select r.descriptor, r.status, s.view, m.meta
       from runs r
       join matches m on m.match_id = r.match_id
       left join run_state s on s.run_id = r.run_id
      where r.run_id = $1`,
    [runId],
  );
  if (rows.length === 0) {
    const starting = await runInProgress(runId).catch(() => false);
    return starting
      ? Response.json({ status: "starting" }, { status: 202, headers: { "cache-control": "no-store" } })
      : Response.json({ error: "no such run" }, { status: 404 });
  }
  const row = rows[0];
  const body: RunSnapshot = {
    run: row.descriptor,
    status: row.status,
    view: row.view,
    match: row.meta,
    server_time: Date.now(),
  };
  return Response.json(body, { headers: { "cache-control": "no-store" } });
}

export async function DELETE(_request: NextRequest, ctx: RouteContext<"/api/runs/[runId]">) {
  const { runId } = await ctx.params;
  if (!runIdPattern.test(runId)) return Response.json({ error: "not a run ID" }, { status: 400 });
  return (await stopRun(runId)) ? new Response(null, { status: 204 }) : Response.json({ error: "no such run in progress" }, { status: 404 });
}
