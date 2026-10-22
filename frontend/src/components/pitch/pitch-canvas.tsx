"use client";

import { useEffect, useRef } from "react";

import type { Club, TrackingLayout } from "@/lib/live/contract";
import type { Frame } from "@/lib/live/tracking";

// Our own 2D render of the match, standing in for the viewer's video: every player and the ball as
// of the viewer's playback, drawn from the tracking (docs/data.md). Metres in the feed's absolute
// frame, x along the pitch and y across it, scaled to the canvas.

export const LENGTH = 105;
export const WIDTH = 68;
export const MARGIN = 3; // metres of surround drawn outside the lines
const PLAYER_RADIUS = 1.15;

const GRASS = "#2f6b3a";
const GRASS_STRIPE = "#336f3e";
const LINE = "rgba(255,255,255,0.85)";

export interface PitchPlayer {
  shirt: number;
  side: 0 | 1; // 0 home, 1 away
}

export function drawPitch(ctx: CanvasRenderingContext2D, s: number, calm: boolean) {
  const w = (LENGTH + 2 * MARGIN) * s;
  const h = (WIDTH + 2 * MARGIN) * s;
  ctx.fillStyle = GRASS;
  ctx.fillRect(0, 0, w, h);
  if (!calm) {
    ctx.fillStyle = GRASS_STRIPE;
    for (let i = 0; i < 14; i += 2) ctx.fillRect((MARGIN + (i * LENGTH) / 14) * s, MARGIN * s, (LENGTH / 14) * s, WIDTH * s);
  }
  ctx.save();
  ctx.translate(MARGIN * s, MARGIN * s);
  ctx.strokeStyle = LINE;
  ctx.lineWidth = Math.max(1, 0.15 * s);
  ctx.strokeRect(0, 0, LENGTH * s, WIDTH * s);
  ctx.beginPath();
  ctx.moveTo((LENGTH / 2) * s, 0);
  ctx.lineTo((LENGTH / 2) * s, WIDTH * s);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc((LENGTH / 2) * s, (WIDTH / 2) * s, 9.15 * s, 0, Math.PI * 2);
  ctx.stroke();
  for (const end of [0, 1]) {
    const x = (d: number) => (end === 0 ? d : LENGTH - d) * s;
    const box = (depth: number, half: number) => {
      ctx.beginPath();
      ctx.moveTo(x(0), (WIDTH / 2 - half) * s);
      ctx.lineTo(x(depth), (WIDTH / 2 - half) * s);
      ctx.lineTo(x(depth), (WIDTH / 2 + half) * s);
      ctx.lineTo(x(0), (WIDTH / 2 + half) * s);
      ctx.stroke();
    };
    box(16.5, 20.16);
    box(5.5, 9.16);
    ctx.beginPath();
    ctx.arc(x(11), (WIDTH / 2) * s, 9.15 * s, end === 0 ? -0.927 : Math.PI - 0.927, end === 0 ? 0.927 : Math.PI + 0.927);
    ctx.stroke();
    ctx.fillStyle = LINE;
    ctx.beginPath();
    ctx.arc(x(11), (WIDTH / 2) * s, 0.25 * s, 0, Math.PI * 2);
    ctx.fill();
    ctx.lineWidth = Math.max(2, 0.3 * s);
    ctx.beginPath();
    ctx.moveTo(x(0), (WIDTH / 2 - 3.66) * s);
    ctx.lineTo(x(0), (WIDTH / 2 + 3.66) * s);
    ctx.stroke();
    ctx.lineWidth = Math.max(1, 0.15 * s);
  }
  ctx.restore();
}

export function drawFrame(
  ctx: CanvasRenderingContext2D,
  s: number,
  frame: Frame,
  layout: TrackingLayout,
  players: Map<string, PitchPlayer>,
  clubs: [Club, Club],
  focus: string | null,
) {
  ctx.save();
  ctx.translate(MARGIN * s, MARGIN * s);
  const lineup = layout.slot_players[frame.lineup] ?? layout.slot_players[0];
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.font = `600 ${Math.max(8, 1.25 * s)}px ui-sans-serif, system-ui, sans-serif`;
  frame.players.forEach((p, slot) => {
    if (!p) return;
    const id = lineup[slot];
    const who = players.get(id);
    const side = slot < 11 ? 0 : 1;
    const club = clubs[side];
    const x = p.x * s;
    const y = p.y * s;
    if (id === focus) {
      ctx.strokeStyle = "#facc15";
      ctx.lineWidth = Math.max(2, 0.35 * s);
      ctx.beginPath();
      ctx.arc(x, y, (PLAYER_RADIUS + 0.7) * s, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.fillStyle = club.colours[0];
    ctx.strokeStyle = club.colours[1];
    ctx.lineWidth = Math.max(1, 0.22 * s);
    ctx.beginPath();
    ctx.arc(x, y, PLAYER_RADIUS * s, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    if (who && s >= 5) {
      ctx.fillStyle = club.colours[1];
      ctx.fillText(String(who.shirt), x, y + 0.05 * s);
    }
  });
  // The ball's shadow stays on the ground; the ball rises above it and grows a little with height.
  const { x, y, z } = frame.ball;
  ctx.fillStyle = "rgba(0,0,0,0.35)";
  ctx.beginPath();
  ctx.arc(x * s, y * s, 0.45 * s, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#ffffff";
  ctx.strokeStyle = "#111111";
  ctx.lineWidth = Math.max(1, 0.1 * s);
  ctx.beginPath();
  ctx.arc(x * s, (y - Math.min(z, 12) * 0.35) * s, (0.5 + Math.min(z, 12) * 0.04) * s, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.restore();
}

/**
 * Draws `frameAt(...)` for the moment `current()` names, on every animation frame. `current` returns
 * the period and seconds into it the viewer's playback shows, or null in the half-time break.
 */
export function PitchCanvas({
  layout,
  frameAt,
  current,
  players,
  clubs,
  focus,
  calm,
  label,
}: {
  layout: TrackingLayout;
  frameAt: (period: number, t: number) => Frame | null;
  current: () => { period: number; t: number } | null;
  players: Map<string, PitchPlayer>;
  clubs: [Club, Club];
  focus: string | null;
  calm: boolean;
  label: string;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
    const ctx = el.getContext("2d");
    if (!ctx) return;
    let raf = 0;
    let last: Frame | null = null;
    const draw = () => {
      const ratio = window.devicePixelRatio || 1;
      const cssWidth = el.clientWidth;
      const cssHeight = (cssWidth * (WIDTH + 2 * MARGIN)) / (LENGTH + 2 * MARGIN);
      if (el.width !== Math.round(cssWidth * ratio) || el.height !== Math.round(cssHeight * ratio)) {
        el.width = Math.round(cssWidth * ratio);
        el.height = Math.round(cssHeight * ratio);
      }
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      const s = cssWidth / (LENGTH + 2 * MARGIN);
      drawPitch(ctx, s, calm);
      const at = current();
      const frame = at ? frameAt(at.period, at.t) : null;
      // While the next frames are on their way, the last one stays, as a stalled stream would.
      if (frame) last = frame;
      if (at && last) drawFrame(ctx, s, last, layout, players, clubs, focus);
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [layout, frameAt, current, players, clubs, focus, calm]);

  return (
    <canvas
      ref={canvas}
      role="img"
      aria-label={label}
      className="block aspect-111/74 w-full rounded-xl bg-[#2f6b3a]"
    />
  );
}
