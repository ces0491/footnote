"use client";

import { WebPubSubClient } from "@azure/web-pubsub-client";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import type { PushMessage, RunSnapshot } from "@/lib/live/contract";
import { initialRunViewState, runReducer } from "@/lib/live/run-reducer";

export type Connection = "connecting" | "connected" | "reconnecting" | "closed";

export interface Latency {
  p50: number;
  p95: number;
  samples: number;
}

const LATENCY_WINDOW = 200;

function percentile(sorted: number[], p: number): number {
  return sorted[Math.min(sorted.length - 1, Math.floor(p * sorted.length))];
}

/** Server clock minus browser clock, from the quickest of a few round trips. */
async function clockOffset(): Promise<number> {
  let best = { rtt: Infinity, offset: 0 };
  for (let i = 0; i < 3; i++) {
    const sent = Date.now();
    const { now } = (await (await fetch("/api/time", { cache: "no-store" })).json()) as { now: number };
    const received = Date.now();
    if (received - sent < best.rtt) best = { rtt: received - sent, offset: now - (sent + received) / 2 };
  }
  return best.offset;
}

async function fetchSnapshot(runId: string, signal: AbortSignal): Promise<RunSnapshot> {
  // The processor records a run within a second or two of its start; until then the API says 202.
  for (let attempt = 0; ; attempt++) {
    const response = await fetch(`/api/runs/${runId}`, { cache: "no-store", signal });
    if (response.status === 202 && attempt < 30) {
      await new Promise((resolve) => setTimeout(resolve, 500));
      continue;
    }
    if (response.status === 200) return (await response.json()) as RunSnapshot;
    throw new Error(response.status === 404 ? "There's no such replay." : `run ${runId}: HTTP ${response.status}`);
  }
}

async function clientAccessUrl(runId: string): Promise<string> {
  const response = await fetch(`/api/runs/${runId}/negotiate`, { cache: "no-store" });
  if (!response.ok) throw new Error(`negotiate: HTTP ${response.status}`);
  return ((await response.json()) as { url: string }).url;
}

/**
 * Follow a run. The page shows the stored snapshot first, and a run that has already ended stops
 * there. For a run in progress it joins the run's Web PubSub group and fetches the snapshot again
 * each time a connection opens, since pushes sent while there was none are lost. The reducer holds
 * pushes while a snapshot is on its way, applies them on top of it, and asks for another after a gap.
 */
export function useLiveRun(runId: string) {
  const [state, dispatch] = useReducer(runReducer, initialRunViewState);
  const [snapshot, setSnapshot] = useState<RunSnapshot | null>(null);
  const [connection, setConnection] = useState<Connection>("connecting");
  const [error, setError] = useState<string | null>(null);
  const [latency, setLatency] = useState<Latency | null>(null);
  const [offset, setOffset] = useState(0);
  const offsetRef = useRef(0);
  const samples = useRef<number[]>([]);
  const client = useRef<WebPubSubClient | null>(null);

  const applySnapshot = useCallback((loaded: RunSnapshot) => {
    setSnapshot(loaded);
    dispatch({ kind: "snapshot", view: loaded.view, ended: loaded.status === "running" ? null : loaded.status });
  }, []);

  useEffect(() => {
    const abort = new AbortController();
    samples.current = [];

    const ws = new WebPubSubClient({ getClientAccessUrl: () => clientAccessUrl(runId) });
    client.current = ws;
    // Fires once per new connection (a recovered one keeps its messages), so catch up each time.
    ws.on("connected", () => {
      setConnection("connected");
      dispatch({ kind: "resync" });
    });
    ws.on("disconnected", () => setConnection("reconnecting"));
    ws.on("stopped", () => setConnection("closed"));
    ws.on("group-message", (e) => {
      // The processor sends compact JSON as text (src/footnote/live/contract.py, wire); a JSON
      // payload is taken as it comes.
      const data = e.message.data;
      const message = (typeof data === "string" ? JSON.parse(data) : data) as PushMessage;
      if (message.type === "event" && message.timing.published_at) {
        const elapsed = Date.now() + offsetRef.current - message.timing.published_at;
        const window = samples.current;
        window.push(elapsed);
        if (window.length > LATENCY_WINDOW) window.shift();
        const sorted = [...window].sort((a, b) => a - b);
        setLatency({ p50: percentile(sorted, 0.5), p95: percentile(sorted, 0.95), samples: sorted.length });
      }
      dispatch({ kind: "push", message });
    });

    (async () => {
      try {
        const [measured, first] = await Promise.all([clockOffset(), fetchSnapshot(runId, abort.signal)]);
        if (abort.signal.aborted) return;
        offsetRef.current = measured;
        setOffset(measured);
        applySnapshot(first);
        // An ended run sends nothing more, so there is nothing to connect for.
        if (first.status !== "running") {
          setConnection("closed");
          return;
        }
        await ws.start();
      } catch (cause) {
        if (!abort.signal.aborted) setError(cause instanceof Error ? cause.message : String(cause));
      }
    })();

    return () => {
      abort.abort();
      ws.stop();
      client.current = null;
    };
  }, [runId, applySnapshot]);

  // Fetch the snapshot each time the reducer asks for one: on connecting and after a missed push.
  useEffect(() => {
    if (state.snapshotRequests === 0) return;
    const abort = new AbortController();
    fetchSnapshot(runId, abort.signal).then(
      (loaded) => {
        if (!abort.signal.aborted) applySnapshot(loaded);
      },
      (cause) => {
        if (!abort.signal.aborted) setError(String(cause));
      },
    );
    return () => abort.abort();
  }, [state.snapshotRequests, runId, applySnapshot]);

  // A finished run sends nothing more; free the connection (the free tier allows 20 in all).
  useEffect(() => {
    if (state.ended) client.current?.stop();
  }, [state.ended]);

  return { view: state.view, ended: state.ended, snapshot, connection, error, latency, offset };
}
