import type { NextRequest } from "next/server";

import { runIdPattern } from "@/lib/live/contract";
import { db } from "@/lib/server/db";
import { clientUrl } from "@/lib/server/webpubsub";

// A Web PubSub client URL for the run's group, valid for an hour, for a run the processor has
// recorded. A run that has ended still gets one: a page reconnecting after the end learns it from the
// snapshot it fetches on connecting, while a refusal would leave the client retrying every second.
export async function GET(_request: NextRequest, ctx: RouteContext<"/api/runs/[runId]/negotiate">) {
  const { runId } = await ctx.params;
  if (!runIdPattern.test(runId)) return Response.json({ error: "not a run ID" }, { status: 400 });
  const { rows } = await db().query("select 1 from runs where run_id = $1", [runId]);
  if (rows.length === 0) return Response.json({ error: "no such run" }, { status: 404 });
  return Response.json({ url: await clientUrl(runId) }, { headers: { "cache-control": "no-store" } });
}
