import "server-only";

import type { RunDescriptor, StartRunRequest } from "@/lib/live/contract";

import { serverEnv } from "./env";

export class ReplayerError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function call(path: string, init: RequestInit): Promise<Response> {
  const response = await fetch(`${serverEnv().REPLAYER_URL}${path}`, {
    ...init,
    cache: "no-store",
    signal: AbortSignal.timeout(10_000),
  });
  if (!response.ok && response.status !== 404) {
    throw new ReplayerError(response.status, await response.text());
  }
  return response;
}

export async function startRun(request: StartRunRequest): Promise<RunDescriptor> {
  const response = await call("/runs", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(request),
  });
  return (await response.json()) as RunDescriptor;
}

/** False when the replayer has no such run in progress; a ReplayerError (403) when `viewer` isn't
 * the one who started it. */
export async function stopRun(runId: string, viewer: string): Promise<boolean> {
  const response = await call(`/runs/${runId}`, {
    method: "DELETE",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ viewer }),
  });
  return response.status === 204;
}

export async function runInProgress(runId: string): Promise<boolean> {
  const response = await call(`/runs/${runId}`, { method: "GET" });
  return response.ok;
}
