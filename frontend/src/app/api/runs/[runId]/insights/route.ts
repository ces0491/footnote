import type { NextRequest } from "next/server";

import { counterParam, type InsightPushesResponse, runIdPattern } from "@/lib/live/contract";
import { db } from "@/lib/server/db";

const PAGE = 500;

// Every insight change the run's viewers were pushed after revision `after`, as each writer sent it
// (migration 0005). A page that loads after a card changed, or that missed pushes, keeps the card's
// earlier states, so a fan whose stream runs behind sees each card as it stood at their playback
// (lib/live/playback.ts). GET /api/runs/[runId]/insights?after=12
export async function GET(request: NextRequest, ctx: RouteContext<"/api/runs/[runId]/insights">) {
  const { runId } = await ctx.params;
  if (!runIdPattern.test(runId)) return Response.json({ error: "not a run ID" }, { status: 400 });
  const after = counterParam(request.nextUrl.searchParams.get("after"));
  if (after === null) return Response.json({ error: "after: an insight revision" }, { status: 400 });
  const { rows } = await db().query(
    `select push from insight_pushes
      where run_id = $1 and rev > $2
      order by rev
      limit $3`,
    [runId, after ?? 0, PAGE],
  );
  const body: InsightPushesResponse = { pushes: rows.map((r) => r.push), more: rows.length === PAGE };
  return Response.json(body, { headers: { "cache-control": "no-store" } });
}
