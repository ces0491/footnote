import type { NextRequest } from "next/server";

import { runIdPattern, type RunSnapshot, stopRunRequest } from "@/lib/live/contract";
import { jsonBody } from "@/lib/server/body";
import { db } from "@/lib/server/db";
import { ReplayerError, runInProgress, stopRun } from "@/lib/server/replayer";

// The run's descriptor, its latest state view, its insights, how its graphics are approved, and the
// match metadata and tracking layout, from Postgres. One statement reads them all, so the insights
// and the revision they are as of agree. The processor records a run within a second or two of its
// start; until then the answer is 202 for a run the replayer is playing, and 404 for one it doesn't
// know.
export async function GET(_request: NextRequest, ctx: RouteContext<"/api/runs/[runId]">) {
  const { runId } = await ctx.params;
  if (!runIdPattern.test(runId)) return Response.json({ error: "not a run ID" }, { status: 400 });
  const { rows } = await db().query(
    `select r.descriptor, r.status, r.insight_rev, r.producer, s.view, m.meta, m.tracking - 'digest' as tracking,
            coalesce((select jsonb_agg(to_jsonb(c) - 'run_id' order by c.seq, c.insight_id)
                        from insight_cards c where c.run_id = r.run_id), '[]'::jsonb) as insights
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
    producer: row.producer,
    view: row.view,
    match: row.meta,
    tracking: row.tracking,
    insights: row.insights,
    insight_rev: row.insight_rev,
    server_time: Date.now(),
  };
  return Response.json(body, { headers: { "cache-control": "no-store" } });
}

// Stop a replay: { viewer }, the anonymous ID of the browser that started it, which alone may stop
// it, as it alone may produce it. JSON only, like starting one.
export async function DELETE(request: NextRequest, ctx: RouteContext<"/api/runs/[runId]">) {
  const { runId } = await ctx.params;
  if (!runIdPattern.test(runId)) return Response.json({ error: "not a run ID" }, { status: 400 });
  if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) {
    return Response.json({ error: "send JSON" }, { status: 415 });
  }
  const body = await jsonBody(request);
  if ("response" in body) return body.response;
  const parsed = stopRunRequest.safeParse(body.value);
  if (!parsed.success) return Response.json({ error: "viewer: the ID of the browser that started it" }, { status: 422 });
  try {
    return (await stopRun(runId, parsed.data.viewer))
      ? new Response(null, { status: 204 })
      : Response.json({ error: "no such run in progress" }, { status: 404 });
  } catch (error) {
    if (error instanceof ReplayerError && error.status === 403) {
      return Response.json({ error: "Only the browser that started this replay can stop it." }, { status: 403 });
    }
    console.error("stopping a run failed", error);
    return Response.json({ error: "the replayer didn't answer" }, { status: 502 });
  }
}
