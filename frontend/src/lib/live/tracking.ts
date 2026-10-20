// The tracking the pitch view draws (src/footnote/live/pitch.py): each frame is `values_per_frame`
// little-endian int16 values, the 22 slots' x and y and the ball's x, y and z in centimetres
// (-32768 for an empty slot), then the index of the line-up in force. Chunk n of a period holds its
// frames from n * frames_per_chunk. The web app serves a run's viewers the frames up to its live
// point and none beyond.

import type { TrackingLayout } from "./contract";
import type { Moment } from "./timeline";

export const SLOTS = 22;
export const EMPTY = -32768;

/** How many of a chunk's frames lie at or before `limit`: a live point, or in the half-time break the
 * end of the first half (t: Infinity). */
export function framesUpTo(layout: TrackingLayout, period: number, chunk: number, limit: Moment): number {
  const total = layout.frames[String(period)] ?? 0;
  const start = chunk * layout.frames_per_chunk;
  const inChunk = Math.max(0, Math.min(layout.frames_per_chunk, total - start));
  if (period < limit.period) return inChunk;
  if (period > limit.period) return 0;
  const last = Math.floor(limit.t * layout.frame_rate + 1e-6);
  return Math.max(0, Math.min(inChunk, last - start + 1));
}

/** The chunk holding the frame at `t` seconds into a period. */
export function chunkAt(layout: TrackingLayout, t: number): number {
  return Math.floor(Math.max(0, Math.round(t * layout.frame_rate)) / layout.frames_per_chunk);
}

/** Everyone on the pitch at one instant, in metres. */
export interface Frame {
  players: ({ x: number; y: number } | null)[]; // by slot; null while a slot is empty
  ball: { x: number; y: number; z: number };
  lineup: number; // index into the layout's slot_players
}

function at(values: Int16Array, offset: number): { x: number; y: number } | null {
  const x = values[offset];
  const y = values[offset + 1];
  return x === EMPTY || y === EMPTY ? null : { x: x / 100, y: y / 100 };
}

/** Frame `index` of a chunk's values. */
export function readFrame(values: Int16Array, index: number, valuesPerFrame: number): Frame {
  const base = index * valuesPerFrame;
  const players = Array.from({ length: SLOTS }, (_, slot) => at(values, base + slot * 2));
  const b = base + SLOTS * 2;
  return {
    players,
    ball: { x: values[b] / 100, y: values[b + 1] / 100, z: values[b + 2] / 100 },
    lineup: values[b + 3],
  };
}

/** Between two frames, `f` of the way from `a` to `b`. A slot empty in either stays as `a` has it. */
export function between(a: Frame, b: Frame, f: number): Frame {
  const mix = (p: number, q: number) => p + (q - p) * f;
  return {
    players: a.players.map((p, slot) => {
      const q = b.players[slot];
      return p && q && a.lineup === b.lineup ? { x: mix(p.x, q.x), y: mix(p.y, q.y) } : p;
    }),
    ball: { x: mix(a.ball.x, b.ball.x), y: mix(a.ball.y, b.ball.y), z: mix(a.ball.z, b.ball.z) },
    lineup: a.lineup,
  };
}

/**
 * Where the offside line runs at a pass: level with the defending side's second-last player, on the
 * side the attackers attack (Law 11; the goalkeeper is usually the last). Null when fewer than two of
 * the defending side are on the pitch. `defending` is 0 for the home slots, 1 for the away ones.
 */
export function offsideLine(frame: Frame, defending: 0 | 1, attacking: "+x" | "-x"): number | null {
  const xs = frame.players
    .slice(defending * 11, defending * 11 + 11)
    .filter((p): p is { x: number; y: number } => p !== null)
    .map((p) => p.x)
    .sort((a, b) => (attacking === "+x" ? b - a : a - b));
  return xs.length < 2 ? null : xs[1];
}
