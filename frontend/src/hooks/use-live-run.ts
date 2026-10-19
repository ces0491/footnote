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
  // The processor records a run within a second or two of its start; until then the API says 404.
  for (let attempt = 0; ; attempt++) {
    const response = await fetch(`/api/runs/${runId}`, { cache: "no-store", signal });
    if (response.ok) return (await response.json()) as RunSnapshot;
    if (response.status !== 404 || attempt >= 30) throw new Error(`run ${runId}: HTTP ${response.status}`);
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
}

/**
 * Follow a run: connect to its Web PubSub group first, then fetch the snapshot, then apply pushes.
 * Pushes that arrive before the first snapshot are held and applied after it, so nothing is lost
 * between the two. A gap in seq triggers a fresh snapshot.
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
  const held = useRef<PushMessage[] | null>([]);
  const client = useRef<WebPubSubClient | null>(null);

  const loadSnapshot = useCallback(
    async (signal: AbortSignal) => {
      const loaded = await fetchSnapshot(runId, signal);
      setSnapshot(loaded);
      const ended = loaded.status === "running" ? null : loaded.status;
      dispatch({ kind: "snapshot", view: loaded.view, ended });
      const pending = held.current;
      held.current = null;
      for (const message of pending ?? []) dispatch({ kind: "push", message });
    },
    [runId],
  );

  useEffect(() => {
    const abort = new AbortController();
    held.current = [];
    samples.current = [];

    const ws = new WebPubSubClient({
      getClientAccessUrl: async () => {
        const response = await fetch(`/api/runs/${runId}/negotiate`, { cache: "no-store" });
        if (!response.ok) throw new Error(`negotiate: HTTP ${response.status}`);
        return ((await response.json()) as { url: string }).url;
      },
    });
    client.current = ws;
    ws.on("connected", () => setConnection("connected"));
    ws.on("disconnected", () => setConnection("reconnecting"));
    ws.on("stopped", () => setConnection("closed"));
    ws.on("group-message", (e) => {
      const message = e.message.data as unknown as PushMessage;
      if (message.type === "event" && message.timing.published_at) {
        const elapsed = Date.now() + offsetRef.current - message.timing.published_at;
        const window = samples.current;
        window.push(elapsed);
        if (window.length > LATENCY_WINDOW) window.shift();
        const sorted = [...window].sort((a, b) => a - b);
        setLatency({ p50: percentile(sorted, 0.5), p95: percentile(sorted, 0.95), samples: sorted.length });
      }
      if (held.current) held.current.push(message);
      else dispatch({ kind: "push", message });
    });

    (async () => {
      try {
        const measured = await clockOffset();
        offsetRef.current = measured;
        setOffset(measured);
        await ws.start();
        await loadSnapshot(abort.signal);
      } catch (cause) {
        if (!abort.signal.aborted) setError(cause instanceof Error ? cause.message : String(cause));
      }
    })();

    return () => {
      abort.abort();
      ws.stop();
      client.current = null;
    };
  }, [runId, loadSnapshot]);

  // Refetch after a missed push.
  useEffect(() => {
    if (!state.needsSnapshot || held.current) return;
    const abort = new AbortController();
    loadSnapshot(abort.signal).catch((cause) => {
      if (!abort.signal.aborted) setError(String(cause));
    });
    return () => abort.abort();
  }, [state.needsSnapshot, loadSnapshot]);

  // A finished run sends nothing more; free the connection (the free tier allows 20 in all).
  useEffect(() => {
    if (state.ended) client.current?.stop();
  }, [state.ended]);

  return { ...state, snapshot, connection, error, latency, offset };
}
