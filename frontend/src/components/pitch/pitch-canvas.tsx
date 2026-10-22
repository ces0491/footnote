"use client";

import { useEffect, useRef } from "react";

import { NIGHT } from "@/lib/club-colour";
import type { Club, TrackingLayout } from "@/lib/live/contract";
import type { Frame } from "@/lib/live/tracking";

// Our own 2D render of the match, standing in for the viewer's video: every player and the ball as
// of the viewer's playback, drawn from the tracking (docs/data.md). Metres in the feed's absolute
// frame, x along the pitch and y across it, scaled to the canvas.

export const LENGTH = 105;
export const WIDTH = 68;
export const MARGIN = 3; // metres of surround drawn outside the lines
const PLAYER_RADIUS = 1.15;

// A pitch under floodlights: the grass, its mown stripes, the surround beyond the lines a shade
// darker, and the light falling off towards the corners. The page's colours (app/globals.css) as hex,
// for the canvas.
const GRASS = "#285931";
const GRASS_STRIPE = "#2d6137";
const SURROUND = "#224f2d";
const LINE = "rgba(255,255,255,0.78)";
export const CITE = "#f3d350"; // the followed player, and the offside line
export const TALLY = "#f85452";

export interface PitchPlayer {
  shirt: number;
  side: 0 | 1; // 0 home, 1 away
}

let family: string | null = null;

/** The page's own typeface, condensed, for shirt numbers and labels drawn on a canvas. */
export function canvasFont(ctx: CanvasRenderingContext2D, weight: number, px: number) {
  family ??= getComputedStyle(ctx.canvas).fontFamily || "ui-sans-serif, system-ui, sans-serif";
  ctx.font = `${weight} ${px}px ${family}`;
  ctx.fontStretch = "condensed";
}

export function drawPitch(ctx: CanvasRenderingContext2D, s: number, calm: boolean) {
  const w = (LENGTH + 2 * MARGIN) * s;
  const h = (WIDTH + 2 * MARGIN) * s;
  ctx.fillStyle = SURROUND;
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = GRASS;
  ctx.fillRect(MARGIN * s, MARGIN * s, LENGTH * s, WIDTH * s);
  if (!calm) {
    ctx.fillStyle = GRASS_STRIPE;
    for (let i = 0; i < 14; i += 2) ctx.fillRect((MARGIN + (i * LENGTH) / 14) * s, MARGIN * s, (LENGTH / 14) * s, WIDTH * s);
  }
  const light = ctx.createRadialGradient(w / 2, h / 2, h * 0.25, w / 2, h / 2, w * 0.62);
  light.addColorStop(0, "rgba(0,0,0,0)");
  light.addColorStop(1, "rgba(0,0,0,0.32)");
  ctx.fillStyle = light;
  ctx.fillRect(0, 0, w, h);
  ctx.save();
  ctx.translate(MARGIN * s, MARGIN * s);
  ctx.strokeStyle = LINE;
  ctx.lineWidth = Math.max(1, 0.12 * s);
  ctx.strokeRect(0, 0, LENGTH * s, WIDTH * s);
  ctx.beginPath();
  ctx.moveTo((LENGTH / 2) * s, 0);
  ctx.lineTo((LENGTH / 2) * s, WIDTH * s);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc((LENGTH / 2) * s, (WIDTH / 2) * s, 9.15 * s, 0, Math.PI * 2);
  ctx.stroke();
  ctx.fillStyle = LINE;
  ctx.beginPath();
  ctx.arc((LENGTH / 2) * s, (WIDTH / 2) * s, 0.25 * s, 0, Math.PI * 2);
  ctx.fill();
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
    ctx.beginPath();
    ctx.arc(x(11), (WIDTH / 2) * s, 0.25 * s, 0, Math.PI * 2);
    ctx.fill();
    ctx.lineWidth = Math.max(2, 0.3 * s);
    ctx.beginPath();
    ctx.moveTo(x(0), (WIDTH / 2 - 3.66) * s);
    ctx.lineTo(x(0), (WIDTH / 2 + 3.66) * s);
    ctx.stroke();
    ctx.lineWidth = Math.max(1, 0.12 * s);
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
  canvasFont(ctx, 700, Math.max(8, 1.35 * s));
  frame.players.forEach((p, slot) => {
    if (!p) return;
    const id = lineup[slot];
    const who = players.get(id);
    const side = slot < 11 ? 0 : 1;
    const club = clubs[side];
    const x = p.x * s;
    const y = p.y * s;
    // A soft shadow under each player, so the discs sit on the grass.
    ctx.fillStyle = "rgba(0,0,0,0.28)";
    ctx.beginPath();
    ctx.arc(x + 0.18 * s, y + 0.25 * s, PLAYER_RADIUS * s, 0, Math.PI * 2);
    ctx.fill();
    if (id === focus) {
      ctx.strokeStyle = CITE;
      ctx.lineWidth = Math.max(2, 0.35 * s);
      ctx.beginPath();
      ctx.arc(x, y, (PLAYER_RADIUS + 0.75) * s, 0, Math.PI * 2);
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
      ctx.fillText(String(who.shirt), x, y + 0.08 * s);
    }
  });
  // The ball's shadow stays on the ground; the ball rises above it and grows a little with height.
  const { x, y, z } = frame.ball;
  ctx.fillStyle = "rgba(0,0,0,0.4)";
  ctx.beginPath();
  ctx.arc(x * s, y * s, 0.45 * s, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#ffffff";
  ctx.strokeStyle = NIGHT;
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

  return <canvas ref={canvas} role="img" aria-label={label} className="block aspect-111/74 w-full bg-[#224f2d]" />;
}
