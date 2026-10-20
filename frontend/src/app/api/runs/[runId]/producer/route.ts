import type { NextRequest } from "next/server";

import { producerModeRequest, runIdPattern } from "@/lib/live/contract";
import { desk } from "@/lib/server/desk";

// How the run's graphics are approved from now on: { viewer, mode: "auto" | "manual" }. The desk
// lets only the viewer who started the replay change it.
export async function POST(request: NextRequest, ctx: RouteContext<"/api/runs/[runId]/producer">) {
  const { runId } = await ctx.params;
  if (!runIdPattern.test(runId)) return Response.json({ error: "not a run ID", problems: [] }, { status: 400 });
  if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) {
    return Response.json({ error: "send the request as application/json", problems: [] }, { status: 415 });
  }
  const parsed = producerModeRequest.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return Response.json({ error: "viewer and mode are needed", problems: [] }, { status: 422 });
  return desk(`/runs/${runId}/producer`, parsed.data);
}
