import { startRunRequest } from "@/lib/live/contract";
import { jsonBody } from "@/lib/server/body";
import { clientAddress, starts } from "@/lib/server/rate-limit";
import { ReplayerError, startRun } from "@/lib/server/replayer";

// Start a replay of the showcase match: { start_minute, speed, viewer? } -> the run descriptor.
export async function POST(request: Request) {
  // JSON only: a form or plain-text post, which another site can send without asking, starts nothing.
  if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) {
    return Response.json({ error: "send the request as application/json" }, { status: 415 });
  }
  const body = await jsonBody(request);
  if ("response" in body) return body.response;
  const parsed = startRunRequest.safeParse(body.value);
  if (!parsed.success) {
    return Response.json({ error: "start_minute must be 1-90 and speed 1, 2 or 4" }, { status: 422 });
  }
  const address = clientAddress(request.headers);
  if (!starts.allow(address)) {
    return Response.json(
      { error: "Too many replays started from here; try again in a few minutes" },
      { status: 429, headers: { "retry-after": String(starts.retryAfter(address)) } },
    );
  }
  try {
    return Response.json(await startRun(parsed.data), { status: 201 });
  } catch (error) {
    console.error("starting a run failed", error);
    const status = error instanceof ReplayerError && error.status < 500 ? error.status : 502;
    return Response.json({ error: "The replayer could not start a run" }, { status });
  }
}
