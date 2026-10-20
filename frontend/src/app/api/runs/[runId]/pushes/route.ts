import type { NextRequest } from "next/server";

import { type PushesResponse, runIdPattern } from "@/lib/live/contract";
import { db } from "@/lib/server/db";

const PAGE = 1_000;

// What the run's viewers were sent after `after`, as the processor stored it with each feed row: the
// snapshot at the end of the backfill, then every event. A viewer whose stream runs behind live
// rebuilds the match as of their own playback from these (lib/live/playback.ts), and any viewer
// fills a gap in what it was pushed. GET /api/runs/[runId]/pushes?after=1563
export async function GET(request: NextRequest, ctx: RouteContext<"/api/runs/[runId]/pushes">) {
  const { runId } = await ctx.params;
  if (!runIdPattern.test(runId)) return Response.json({ error: "not a run ID" }, { status: 400 });
  const after = Number(request.nextUrl.searchParams.get("after") ?? "0");
  if (!Number.isInteger(after) || after < 0) return Response.json({ error: "after: a feed seq" }, { status: 400 });
  const { rows } = await db().query(
    `select push from feed_events
      where run_id = $1 and seq > $2 and push is not null
      order by seq
      limit $3`,
    [runId, after, PAGE],
  );
  const body: PushesResponse = { pushes: rows.map((r) => r.push), more: rows.length === PAGE };
  return Response.json(body, { headers: { "cache-control": "no-store" } });
}
