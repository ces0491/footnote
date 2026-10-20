import { describe, expect, it } from "vitest";

import type { TrackingLayout } from "./contract";
import { between, chunkAt, EMPTY, framesUpTo, offsideLine, readFrame } from "./tracking";

const layout: TrackingLayout = {
  frame_rate: 10,
  frames_per_chunk: 50,
  values_per_frame: 48,
  frames: { "1": 120, "2": 60 },
  slot_players: [Array.from({ length: 22 }, (_, i) => `p${i}`)],
};

function frameValues(x: (slot: number) => number, ball: [number, number, number]): number[] {
  const out: number[] = [];
  for (let slot = 0; slot < 22; slot++) out.push(x(slot), 3400);
  return [...out, ...ball, 0];
}

describe("tracking", () => {
  it("cuts a chunk at the live point and serves whole chunks behind it", () => {
    expect(framesUpTo(layout, 1, 0, { period: 1, t: 20 })).toBe(50);
    expect(framesUpTo(layout, 1, 1, { period: 1, t: 7.45 })).toBe(25); // frames 50 to 74
    expect(framesUpTo(layout, 1, 2, { period: 1, t: 7.45 })).toBe(0);
    expect(framesUpTo(layout, 1, 2, { period: 2, t: 0 })).toBe(20); // the half's last, short chunk
    expect(framesUpTo(layout, 2, 0, { period: 1, t: Infinity })).toBe(0); // in the break
    expect(chunkAt(layout, 7.45)).toBe(1);
  });

  it("reads frames in metres, empty slots as none, and moves between them", () => {
    const values = new Int16Array([
      ...frameValues((slot) => (slot === 21 ? EMPTY : 1000 + slot * 100), [5250, 3400, 0]),
      ...frameValues((slot) => (slot === 21 ? EMPTY : 1100 + slot * 100), [5350, 3400, 50]),
    ]);
    const a = readFrame(values, 0, 48);
    const b = readFrame(values, 1, 48);
    expect(a.players[0]).toEqual({ x: 10, y: 34 });
    expect(a.players[21]).toBeNull();
    expect(a.ball).toEqual({ x: 52.5, y: 34, z: 0 });
    const half = between(a, b, 0.5);
    expect(half.players[0]).toEqual({ x: 10.5, y: 34 });
    expect(half.ball.z).toBeCloseTo(0.25);
  });

  it("puts the offside line level with the second-last defender, towards the goal attacked", () => {
    // Away defends slots 11-21; their x from 60 m (slot 11) to 100 m (slot 21, the goalkeeper).
    const values = new Int16Array(frameValues((slot) => (slot < 11 ? 5000 : 6000 + (slot - 11) * 400), [5000, 3400, 0]));
    const frame = readFrame(values, 0, 48);
    expect(offsideLine(frame, 1, "+x")).toBe(96); // the goalkeeper at 100 m is last
    expect(offsideLine(frame, 1, "-x")).toBe(64);
  });
});
