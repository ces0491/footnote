import type { NextRequest } from "next/server";

import { runIdPattern } from "@/lib/live/contract";
import { clientUrl } from "@/lib/server/webpubsub";

// A Web PubSub client URL for the run's group, valid for an hour. The client asks again to reconnect.
export async function GET(_request: NextRequest, ctx: RouteContext<"/api/runs/[runId]/negotiate">) {
  const { runId } = await ctx.params;
  if (!runIdPattern.test(runId)) return Response.json({ error: "not a run ID" }, { status: 400 });
  return Response.json({ url: await clientUrl(runId) }, { headers: { "cache-control": "no-store" } });
}
