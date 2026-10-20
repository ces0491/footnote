import "server-only";

import { serverEnv } from "./env";

// The producer's desk in the agents service (src/footnote/agents/desk.py), reachable only inside the
// Container Apps environment. It checks who may produce a run and every edit, so the web app passes
// requests on and answers with what the desk said.
export async function desk(path: string, body: unknown): Promise<Response> {
  try {
    const response = await fetch(`${serverEnv().DESK_URL}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
    const answer = await response.json().catch(() => ({ error: "The producer's desk gave no answer", problems: [] }));
    return Response.json(answer, { status: response.status, headers: { "cache-control": "no-store" } });
  } catch (error) {
    console.error("the producer's desk didn't answer", error);
    return Response.json({ error: "The producer's desk isn't answering; try again", problems: [] }, { status: 502 });
  }
}
