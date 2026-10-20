import { startRunRequest } from "@/lib/live/contract";
import { allowStart, clientAddress } from "@/lib/server/rate-limit";
import { ReplayerError, startRun } from "@/lib/server/replayer";

// Start a replay of the showcase match: { start_minute, speed, viewer? } -> the run descriptor.
export async function POST(request: Request) {
  // JSON only: a form or plain-text post, which another site can send without asking, starts nothing.
  if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) {
    return Response.json({ error: "send the request as application/json" }, { status: 415 });
  }
  const parsed = startRunRequest.safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    return Response.json({ error: "start_minute must be 1-90 and speed 1, 2 or 4" }, { status: 422 });
  }
  if (!allowStart(clientAddress(request.headers))) {
    return Response.json({ error: "Too many replays started from here; try again in a few minutes" }, { status: 429 });
  }
  try {
    return Response.json(await startRun(parsed.data), { status: 201 });
  } catch (error) {
    console.error("starting a run failed", error);
    const status = error instanceof ReplayerError && error.status < 500 ? error.status : 502;
    return Response.json({ error: "The replayer could not start a run" }, { status });
  }
}
