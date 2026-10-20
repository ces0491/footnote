"use client";

import { WebPubSubClient } from "@azure/web-pubsub-client";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import type { PushMessage, RunSnapshot } from "@/lib/live/contract";
import { initialRunViewState, runReducer } from "@/lib/live/run-reducer";

// "polling": no push connection (refused, or the negotiate call failed), so the page fetches the
// snapshot every few seconds and tries the connection again now and then.
export type Connection = "connecting" | "connected" | "reconnecting" | "polling" | "closed";

export interface Latency {
  p50: number;
  p95: number;
  samples: number;
}

const LATENCY_WINDOW = 200;
// Waits before retrying a snapshot fetch that failed, in ms; the last one repeats.
const RETRY_MS = [1_000, 2_000, 4_000, 8_000];
// Tries at the first snapshot before the page gives up: with nothing to show, an error says more.
const FIRST_LOAD_TRIES = 4;
const POLL_MS = 3_000;
const RECONNECT_MS = 30_000;

class NoSuchRun extends Error {}

function percentile(sorted: number[], p: number): number {
  return sorted[Math.min(sorted.length - 1, Math.floor(p * sorted.length))];
}

function reason(cause: unknown): string {
  return cause instanceof Error ? cause.message : String(cause);
}

/** Resolves after `ms`, or as soon as `signal` aborts. */
function pause(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        resolve();
      },
      { once: true },
    );
  });
}

/** Server clock minus browser clock, from the quickest of a few round trips; 0 if it can't be had. */
async function clockOffset(): Promise<number> {
  let best = { rtt: Infinity, offset: 0 };
  try {
    for (let i = 0; i < 3; i++) {
      const sent = Date.now();
      const { now } = (await (await fetch("/api/time", { cache: "no-store" })).json()) as { now: number };
      const received = Date.now();
      if (received - sent < best.rtt) best = { rtt: received - sent, offset: now - (sent + received) / 2 };
    }
  } catch {
    // The clock runs a little off; the replay still plays.
  }
  return best.offset;
}

async function fetchSnapshot(runId: string, signal: AbortSignal): Promise<RunSnapshot> {
  // The processor records a run within a second or two of its start; until then the API says 202.
  for (let attempt = 0; ; attempt++) {
    const response = await fetch(`/api/runs/${runId}`, { cache: "no-store", signal });
    if (response.status === 202 && attempt < 30) {
      await pause(500, signal);
      continue;
    }
    if (response.status === 200) return (await response.json()) as RunSnapshot;
    if (response.status === 404) throw new NoSuchRun("There's no such replay.");
    throw new Error(`HTTP ${response.status}`);
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
 *
 * Once something is on screen it stays there. A snapshot fetch that fails is retried with backoff
 * (`trouble` says so meanwhile), and a push connection that can't be opened is replaced by polling
 * the snapshot until it can. `error` is only for a page with nothing to show.
 */
export function useLiveRun(runId: string) {
  const [state, dispatch] = useReducer(runReducer, initialRunViewState);
  const [snapshot, setSnapshot] = useState<RunSnapshot | null>(null);
  const [connection, setConnection] = useState<Connection>("connecting");
  const [error, setError] = useState<string | null>(null);
  const [trouble, setTrouble] = useState<string | null>(null);
  const [latency, setLatency] = useState<Latency | null>(null);
  const [offset, setOffset] = useState(0);
  const offsetRef = useRef(0);
  const samples = useRef<number[]>([]);
  const stopLive = useRef<(() => void) | null>(null);

  const applySnapshot = useCallback((loaded: RunSnapshot) => {
    setSnapshot(loaded);
    dispatch({
      kind: "snapshot",
      view: loaded.view,
      ended: loaded.status === "running" ? null : loaded.status,
      insights: loaded.insights,
      insightRev: loaded.insight_rev,
    });
  }, []);

  useEffect(() => {
    const abort = new AbortController();
    let client: WebPubSubClient | null = null;
    let poll: ReturnType<typeof setInterval> | undefined;
    let retry: ReturnType<typeof setTimeout> | undefined;
    samples.current = [];

    const startPolling = () => {
      poll ??= setInterval(() => dispatch({ kind: "resync" }), POLL_MS);
    };
    const stopPolling = () => {
      clearInterval(poll);
      poll = undefined;
    };

    function open(): WebPubSubClient {
      const ws = new WebPubSubClient({ getClientAccessUrl: () => clientAccessUrl(runId) });
      // The SDK can finish connecting after stop() (stop is ignored while it connects or recovers),
      // so a client this page has let go of is stopped again whenever it shows signs of life.
      const current = () => {
        if (abort.signal.aborted || ws !== client) {
          ws.stop();
          return false;
        }
        return true;
      };
      // Fires once per new connection (a recovered one keeps its messages), so catch up each time.
      ws.on("connected", () => {
        if (!current()) return;
        stopPolling();
        setConnection("connected");
        dispatch({ kind: "resync" });
      });
      // The SDK reconnects on its own; the page keeps moving by polling until it has.
      ws.on("disconnected", () => {
        if (!current()) return;
        setConnection("reconnecting");
        startPolling();
      });
      ws.on("stopped", () => {
        if (current()) setConnection("closed");
      });
      ws.on("group-message", (e) => {
        if (!current()) return;
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
      return ws;
    }

    async function connect(): Promise<void> {
      client?.stop();
      const ws = open();
      client = ws;
      try {
        await ws.start();
      } catch {
        if (abort.signal.aborted || ws !== client) return;
        // Refused (the free tier allows 20 connections in all) or no token: follow by polling the
        // snapshot, and try for a connection again in a while.
        ws.stop();
        setConnection("polling");
        startPolling();
        retry = setTimeout(() => void connect(), RECONNECT_MS);
      }
    }

    stopLive.current = () => {
      stopPolling();
      clearTimeout(retry);
      client?.stop();
    };

    (async () => {
      const measured = clockOffset();
      for (let attempt = 0; ; attempt++) {
        try {
          const first = await fetchSnapshot(runId, abort.signal);
          if (abort.signal.aborted) return;
          offsetRef.current = await measured;
          setOffset(offsetRef.current);
          applySnapshot(first);
          // An ended run sends nothing more, so there is nothing to connect for.
          if (first.status !== "running") {
            setConnection("closed");
            return;
          }
          await connect();
          return;
        } catch (cause) {
          if (abort.signal.aborted) return;
          if (cause instanceof NoSuchRun || attempt + 1 >= FIRST_LOAD_TRIES) {
            setError(cause instanceof NoSuchRun ? cause.message : `Couldn't load the replay: ${reason(cause)}`);
            return;
          }
          await pause(RETRY_MS[Math.min(attempt, RETRY_MS.length - 1)], abort.signal);
        }
      }
    })();

    return () => {
      abort.abort();
      stopLive.current?.();
      stopLive.current = null;
      client = null;
    };
  }, [runId, applySnapshot]);

  // Fetch the snapshot each time the reducer asks for one: on connecting, after a missed push, and
  // on each poll. A failure keeps what is on screen and tries again, backing off.
  useEffect(() => {
    if (state.snapshotRequests === 0) return;
    const abort = new AbortController();
    (async () => {
      for (let attempt = 0; ; attempt++) {
        try {
          const loaded = await fetchSnapshot(runId, abort.signal);
          if (abort.signal.aborted) return;
          setTrouble(null);
          applySnapshot(loaded);
          return;
        } catch (cause) {
          if (abort.signal.aborted) return;
          setTrouble(`Couldn't refresh the replay (${reason(cause)}); trying again.`);
          await pause(RETRY_MS[Math.min(attempt, RETRY_MS.length - 1)], abort.signal);
          if (abort.signal.aborted) return;
        }
      }
    })();
    return () => abort.abort();
  }, [state.snapshotRequests, runId, applySnapshot]);

  // A finished run sends nothing more; free the connection (the free tier allows 20 in all).
  useEffect(() => {
    if (state.ended) stopLive.current?.();
  }, [state.ended]);

  return {
    view: state.view,
    insights: state.insights,
    ended: state.ended,
    snapshot,
    connection: state.ended ? ("closed" as const) : connection,
    error,
    trouble,
    latency,
    offset,
  };
}
