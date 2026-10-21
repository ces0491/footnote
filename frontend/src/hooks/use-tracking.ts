"use client";

import { useCallback, useEffect, useRef } from "react";

import type { RunDescriptor, TrackingLayout } from "@/lib/live/contract";
import { moment } from "@/lib/live/timeline";
import { between, chunkAt, type Frame, readFrame } from "@/lib/live/tracking";

const LOOK_BEHIND = 2; // replay seconds kept behind playback
const LOOK_AHEAD = 12; // replay seconds fetched ahead of playback, as far as live allows
const TICK_MS = 250;
// How often a chunk live is still inside is fetched again: the frames it gains must arrive before
// playback needs them. With a lead under NEAR_LIVE_SECONDS of real time (a 3 s delay at 4x), a fetch
// every 750 ms plus the round trip would let playback catch up, so it goes every tick instead.
const REFETCH_MS = 750;
const NEAR_LIVE_SECONDS = 1.2;

interface Chunk {
  values: Int16Array;
  complete: boolean;
}

/** The chunks covering replay seconds `from` to `to`, by period, skipping the half-time break. */
function chunksBetween(layout: TrackingLayout, run: RunDescriptor, from: number, to: number): [number, number][] {
  const out: [number, number][] = [];
  const start = moment(from, run.timeline) ?? { period: 2 as const, t: 0 };
  const end = moment(to, run.timeline) ?? { period: 1 as const, t: run.timeline.first_half_end };
  for (const period of [1, 2] as const) {
    if (period < start.period || period > end.period) continue;
    const frames = layout.frames[String(period)] ?? 0;
    const last = Math.max(0, Math.ceil(frames / layout.frames_per_chunk) - 1);
    const first = period === start.period ? chunkAt(layout, start.t) : 0;
    const final = period === end.period ? Math.min(last, chunkAt(layout, end.t)) : last;
    for (let c = first; c <= final; c++) out.push([period, c]);
  }
  return out;
}

/**
 * The tracking around a viewer's playback, fetched chunk by chunk as playback moves. The web app
 * sends nothing beyond the run's live point, so a chunk playback hasn't reached yet comes back short
 * and is fetched again. `frameAt` gives the positions at any moment the page has, interpolated
 * between frames, or null where it has none yet.
 */
export function useTracking(
  runId: string,
  run: RunDescriptor | null,
  layout: TrackingLayout | null,
  position: () => { at: number; live: number },
) {
  const chunks = useRef(new Map<string, Chunk>());
  const inFlight = useRef(new Set<string>());
  const positionRef = useRef(position);
  useEffect(() => {
    positionRef.current = position;
  }, [position]);

  useEffect(() => {
    if (!run || !layout) return;
    const store = chunks.current;
    const fetching = inFlight.current;
    const tried = new Map<string, number>(); // when each chunk was last asked for
    const abort = new AbortController();

    async function load(period: number, chunk: number) {
      const key = `${period}:${chunk}`;
      fetching.add(key);
      tried.set(key, Date.now());
      try {
        const response = await fetch(`/api/runs/${runId}/tracking/${period}/${chunk}`, { signal: abort.signal });
        if (!response.ok) return;
        const buffer = await response.arrayBuffer();
        if (buffer.byteLength === 0) return;
        // Little-endian int16, as every browser's typed arrays read them.
        const values = new Int16Array(buffer);
        const total = layout!.frames[String(period)] ?? 0;
        const framesHere = Math.min(layout!.frames_per_chunk, total - chunk * layout!.frames_per_chunk);
        store.set(key, { values, complete: buffer.byteLength >= framesHere * layout!.values_per_frame * 2 });
      } catch {
        // Fetched again on the next tick.
      } finally {
        fetching.delete(key);
      }
    }

    function tick() {
      const { at, live } = positionRef.current();
      // Nothing beyond live exists yet, and once a run has ended live stays where it stopped, so a
      // playback past it asks for nothing.
      const wanted = chunksBetween(layout!, run!, at - LOOK_BEHIND, Math.min(live, at + LOOK_AHEAD));
      const keep = new Set(wanted.map(([p, c]) => `${p}:${c}`));
      for (const key of store.keys()) if (!keep.has(key)) store.delete(key);
      for (const key of tried.keys()) if (!keep.has(key)) tried.delete(key);
      const every = (live - at) / run!.speed < NEAR_LIVE_SECONDS ? TICK_MS : REFETCH_MS;
      const now = Date.now();
      for (const [period, chunk] of wanted) {
        const key = `${period}:${chunk}`;
        if (store.get(key)?.complete || fetching.has(key) || now - (tried.get(key) ?? -Infinity) < every) continue;
        void load(period, chunk);
      }
    }

    tick();
    const timer = setInterval(tick, TICK_MS);
    return () => {
      abort.abort();
      clearInterval(timer);
      store.clear();
      fetching.clear();
    };
  }, [runId, run, layout]);

  const frameAt = useCallback(
    (period: number, t: number): Frame | null => {
      if (!layout) return null;
      const exact = t * layout.frame_rate;
      const index = Math.floor(exact);
      const lookup = (i: number): Frame | null => {
        const chunk = Math.floor(i / layout.frames_per_chunk);
        const values = chunks.current.get(`${period}:${chunk}`)?.values;
        const within = i - chunk * layout.frames_per_chunk;
        if (!values || (within + 1) * layout.values_per_frame > values.length) return null;
        return readFrame(values, within, layout.values_per_frame);
      };
      const a = lookup(index);
      if (!a) return null;
      const b = lookup(index + 1);
      return b ? between(a, b, exact - index) : a;
    },
    [layout],
  );

  return frameAt;
}
