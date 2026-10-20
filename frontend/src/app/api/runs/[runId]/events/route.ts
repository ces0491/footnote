import type { NextRequest } from "next/server";

import { type EvidenceResponse, type FeedEvent, runIdPattern } from "@/lib/live/contract";
import { db } from "@/lib/server/db";

const EVENT_ID = /^e\d{4,6}$/;
const MAX_IDS = 24;
// Provider boilerplate and freeze frames, as the pushes leave them out (src/footnote/live/contract.py).
const DROP = new Set(["feed_version", "match_id", "ts", "freeze_frame", "info"]);

// The events an insight cites, each as it stands: a corrected event is returned as its latest
// version. GET /api/runs/[runId]/events?ids=e0391,e0390
export async function GET(request: NextRequest, ctx: RouteContext<"/api/runs/[runId]/events">) {
  const { runId } = await ctx.params;
  if (!runIdPattern.test(runId)) return Response.json({ error: "not a run ID" }, { status: 400 });
  const ids = (request.nextUrl.searchParams.get("ids") ?? "").split(",").filter(Boolean);
  if (ids.length === 0 || ids.length > MAX_IDS || !ids.every((id) => EVENT_ID.test(id))) {
    return Response.json({ error: `ids: 1 to ${MAX_IDS} event IDs` }, { status: 400 });
  }
  const { rows } = await db().query(
    `select distinct on (event_id) body
       from feed_events
      where run_id = $1 and event_id = any($2)
      order by event_id, version desc, seq desc`,
    [runId, ids],
  );
  const events = rows
    .map(({ body }) => (body.type === "amendment" ? { ...body.corrected_event, seq: body.seq } : body) as FeedEvent)
    .map((event) => Object.fromEntries(Object.entries(event).filter(([key]) => !DROP.has(key))) as FeedEvent)
    .sort((a, b) => a.seq - b.seq);
  const body: EvidenceResponse = { events };
  return Response.json(body, { headers: { "cache-control": "no-store" } });
}
