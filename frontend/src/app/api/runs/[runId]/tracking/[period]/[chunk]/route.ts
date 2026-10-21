import type { NextRequest } from "next/server";

import { counterParam, type RunDescriptor, runIdPattern, type TrackingLayout } from "@/lib/live/contract";
import { liveReplaySecond, moment } from "@/lib/live/timeline";
import { framesUpTo } from "@/lib/live/tracking";
import { db } from "@/lib/server/db";

// One chunk of the tracking the pitch view draws, cut at the run's live point: a viewer is never sent
// a frame from beyond it, as a video stream never carries pictures from the future. Once a run has
// ended, its live point stays where it stopped. The body is the chunk's frames as stored
// (lib/live/tracking.ts); a chunk the live point hasn't reached yet comes back empty.
// GET /api/runs/[runId]/tracking/1/24
export async function GET(_request: NextRequest, ctx: RouteContext<"/api/runs/[runId]/tracking/[period]/[chunk]">) {
  const { runId, period: periodText, chunk: chunkText } = await ctx.params;
  const period = Number(periodText);
  const chunk = counterParam(chunkText);
  if (!runIdPattern.test(runId) || (period !== 1 && period !== 2) || chunk === null || chunk === undefined) {
    return Response.json({ error: "a run ID, a period (1 or 2) and a chunk number" }, { status: 400 });
  }
  const { rows } = await db().query(
    `select r.descriptor, extract(epoch from r.ended_at) * 1000 as ended_ms, m.tracking - 'digest' as layout, c.frames
       from runs r
       join matches m on m.match_id = r.match_id
       left join tracking_chunks c on c.match_id = r.match_id and c.period = $2 and c.chunk = $3
      where r.run_id = $1`,
    [runId, period, chunk],
  );
  const row = rows[0];
  if (!row) return Response.json({ error: "no such run" }, { status: 404 });
  const layout = row.layout as TrackingLayout | null;
  const frames = row.frames as Buffer | null;
  if (!layout || !frames) return Response.json({ error: "no such chunk" }, { status: 404 });

  const run = row.descriptor as RunDescriptor;
  const until = row.ended_ms === null ? Date.now() : Math.min(Date.now(), Number(row.ended_ms));
  const limit = moment(liveReplaySecond(run, until), run.timeline) ?? { period: 1 as const, t: Infinity };
  const count = framesUpTo(layout, period, chunk, limit);
  const whole = count * layout.values_per_frame * 2 === frames.length;
  return new Response(new Uint8Array(frames.subarray(0, count * layout.values_per_frame * 2)), {
    headers: {
      "content-type": "application/octet-stream",
      // A chunk the live point has passed never changes; one it is still inside grows.
      "cache-control": whole ? "private, max-age=86400, immutable" : "no-store",
    },
  });
}
