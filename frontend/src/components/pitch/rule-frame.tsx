"use client";

import { useEffect, useRef, useState } from "react";

import type { Club, EvidenceResponse, FeedEvent, Insight, MatchMeta, TrackingLayout } from "@/lib/live/contract";
import { NBSP, type Roster } from "@/lib/live/describe";
import { type Frame, offsideLine, readFrame } from "@/lib/live/tracking";

import { drawFrame, drawPitch, LENGTH, MARGIN, type PitchPlayer, WIDTH } from "./pitch-canvas";

interface Ring {
  player: string | undefined;
  colour: string;
}

/** The offside call up close: margins are often centimetres, a fraction of a pixel on the whole pitch. */
interface Inset {
  line: number; // the offside line's x, in metres
  attacker: number; // the receiver's x as the ball was played
  name: string;
  margin: number; // metres beyond the line, in the direction of attack
}

interface Still {
  frame: Frame;
  rings: Ring[];
  line: number | null; // the offside line's x, for an offside call
  inset: Inset | null;
  spot: { x: number; y: number } | null; // where the incident was, for any other call
  caption: string;
  label: string;
}

/** A distance in words, the unit kept with its figure: centimetres under a metre. */
function distance(metres: number): string {
  return metres < 1 ? `${Math.round(metres * 100)}${NBSP}cm` : `${metres.toFixed(1)}${NBSP}m`;
}

/** Everyone's positions at `event`'s moment, from the tracking the web app serves up to live. */
async function frameAt(runId: string, layout: TrackingLayout, event: FeedEvent): Promise<Frame | null> {
  const index = Math.round(event.t * layout.frame_rate);
  const chunk = Math.floor(index / layout.frames_per_chunk);
  const response = await fetch(`/api/runs/${runId}/tracking/${event.period}/${chunk}`);
  if (!response.ok) return null;
  const values = new Int16Array(await response.arrayBuffer());
  const within = index - chunk * layout.frames_per_chunk;
  if ((within + 1) * layout.values_per_frame > values.length) return null;
  return readFrame(values, within, layout.values_per_frame);
}

/**
 * The still a VAR decision is explained with. Offside is judged when the ball is played, so for an
 * offside call it is the pass the check names, with the line level with the defending side's
 * second-last player; for any other call, the moment the check is about, with the player it names.
 */
async function still(runId: string, insight: Insight, match: MatchMeta, layout: TrackingLayout, r: Roster): Promise<Still | null> {
  // The moment's own events, which name the check and the pass, and those its wording rests on, as
  // they stood at the card's state (components/live/evidence.tsx).
  const ids = [...new Set([...insight.evidence, ...insight.card.evidence])].slice(0, 24);
  const response = await fetch(`/api/runs/${runId}/events?ids=${ids.join(",")}&upto=${insight.shown_seq}`, {
    cache: "no-store",
  });
  if (!response.ok) return null;
  const events = ((await response.json()) as EvidenceResponse).events;
  const name = (id: unknown) => r.player(id)?.name ?? "the player";
  const pass = events.find((e) => e.type === "pass");
  if (insight.fields["moment.incident"] === "offside" && pass) {
    const frame = await frameAt(runId, layout, pass);
    const attackers = match.lineups.find((l) => l.club_id === pass.team_id);
    if (!frame || !attackers) return null;
    const towards = attackers.attacking_direction[pass.period === 1 ? "first_half" : "second_half"];
    const defending: Club = pass.team_id === match.home.id ? match.away : match.home;
    const passer = name(pass.player_id);
    const receiver = name(pass.recipient_id);
    const line = offsideLine(frame, defending.id === match.home.id ? 0 : 1, towards);
    const slots = layout.slot_players[frame.lineup] ?? [];
    const at = typeof pass.recipient_id === "string" ? frame.players[slots.indexOf(pass.recipient_id)] : null;
    const margin = line === null || !at ? null : towards === "+x" ? at.x - line : line - at.x;
    // Drawn only when the tracking puts the receiver beyond the line, as the decision did.
    const inset = line !== null && at && margin !== null && margin > 0 ? { line, attacker: at.x, name: receiver, margin } : null;
    const beyond = inset ? ` ${receiver} was ${distance(inset.margin)} beyond it.` : "";
    return {
      frame,
      rings: [
        { player: pass.player_id, colour: "#ffffff" },
        { player: pass.recipient_id as string | undefined, colour: "#f87171" },
      ],
      line,
      inset,
      spot: null,
      caption: `As ${passer} (white ring) passed to ${receiver} (red ring). The dashed line is level with the second-last ${defending.short_name} player: offside is judged at the moment of the pass, not when the ball arrives.${beyond}`,
      label: `The pitch as ${passer} passed to ${receiver}, with the offside line level with the second-last ${defending.short_name} player.${beyond}`,
    };
  }
  const check = events.find((e) => e.type === "var_check" && e.status === "started");
  if (!check) return null;
  const frame = await frameAt(runId, layout, check);
  if (!frame) return null;
  const subject = name(check.subject_id);
  const incident = insight.fields["moment.incident"] ?? "the incident";
  const spot = typeof check.x === "number" && typeof check.y === "number" ? { x: check.x, y: check.y } : null;
  return {
    frame,
    rings: [{ player: check.subject_id as string | undefined, colour: "#f87171" }],
    line: null,
    inset: null,
    spot,
    caption: `${subject} (red ring) at the moment of the ${incident} claim${spot ? "; the cross marks where it was" : ""}.`,
    label: `The pitch at the moment of the ${incident} claim, with ${subject} ringed`,
  };
}

function draw(el: HTMLCanvasElement, shown: Still, match: MatchMeta, layout: TrackingLayout) {
  const ctx = el.getContext("2d");
  if (!ctx) return;
  const ratio = window.devicePixelRatio || 1;
  const width = el.clientWidth;
  el.width = Math.round(width * ratio);
  el.height = Math.round(((width * (WIDTH + 2 * MARGIN)) / (LENGTH + 2 * MARGIN)) * ratio);
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  const s = width / (LENGTH + 2 * MARGIN);
  drawPitch(ctx, s, true);
  const players = new Map<string, PitchPlayer>();
  for (const lineup of match.lineups) {
    const side = lineup.club_id === match.home.id ? 0 : 1;
    for (const p of [...lineup.starters, ...lineup.bench]) players.set(p.player_id, { shirt: p.shirt, side });
  }
  drawFrame(ctx, s, shown.frame, layout, players, [match.home, match.away], null);
  ctx.save();
  ctx.translate(MARGIN * s, MARGIN * s);
  if (shown.line !== null) {
    ctx.strokeStyle = "#facc15";
    ctx.lineWidth = Math.max(1.5, 0.3 * s);
    ctx.setLineDash([6, 4]);
    ctx.beginPath();
    ctx.moveTo(shown.line * s, 0);
    ctx.lineTo(shown.line * s, WIDTH * s);
    ctx.stroke();
    ctx.setLineDash([]);
  }
  if (shown.spot) {
    const { x, y } = shown.spot;
    ctx.strokeStyle = "#facc15";
    ctx.lineWidth = Math.max(1.5, 0.3 * s);
    ctx.beginPath();
    ctx.moveTo((x - 1.2) * s, (y - 1.2) * s);
    ctx.lineTo((x + 1.2) * s, (y + 1.2) * s);
    ctx.moveTo((x + 1.2) * s, (y - 1.2) * s);
    ctx.lineTo((x - 1.2) * s, (y + 1.2) * s);
    ctx.stroke();
  }
  const slots = layout.slot_players[shown.frame.lineup] ?? [];
  for (const ring of shown.rings) {
    const p = ring.player ? shown.frame.players[slots.indexOf(ring.player)] : null;
    if (!p) continue;
    ctx.strokeStyle = ring.colour;
    ctx.lineWidth = Math.max(2, 0.4 * s);
    ctx.beginPath();
    ctx.arc(p.x * s, p.y * s, 2.2 * s, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.restore();
  if (shown.inset) drawInset(ctx, width, shown.inset);
}

/**
 * The offside line and the receiver up close, in a box in the half away from the action: the two
 * lines a few metres' worth of box apart, however small the margin, with the margin between them.
 */
function drawInset(ctx: CanvasRenderingContext2D, width: number, inset: Inset) {
  const boxWidth = Math.min(180, width * 0.42);
  const boxHeight = boxWidth * 0.6;
  const pad = 8;
  const left = inset.line > LENGTH / 2 ? pad : width - boxWidth - pad;
  const top = pad;
  ctx.save();
  ctx.fillStyle = "rgba(9,9,11,0.82)";
  ctx.strokeStyle = "rgba(255,255,255,0.35)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.roundRect(left, top, boxWidth, boxHeight, 6);
  ctx.fill();
  ctx.stroke();
  // The span shown: the margin in the middle third, and at least 60 cm across.
  const half = Math.max(0.3, inset.margin * 1.5);
  const centre = (inset.line + inset.attacker) / 2;
  const inner = boxWidth - 2 * pad;
  const x = (metres: number) => left + pad + ((metres - (centre - half)) / (2 * half)) * inner;
  const lineTop = top + 22;
  const lineBottom = top + boxHeight - 24;
  ctx.font = "600 11px ui-sans-serif, system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "alphabetic";
  ctx.lineWidth = 2;
  ctx.strokeStyle = "#facc15";
  ctx.setLineDash([5, 3]);
  ctx.beginPath();
  ctx.moveTo(x(inset.line), lineTop);
  ctx.lineTo(x(inset.line), lineBottom);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.strokeStyle = "#f87171";
  ctx.beginPath();
  ctx.moveTo(x(inset.attacker), lineTop);
  ctx.lineTo(x(inset.attacker), lineBottom);
  ctx.stroke();
  // Each label on the outer side of its own line: the two lines can be a few pixels apart.
  const ahead = inset.attacker > inset.line;
  ctx.fillStyle = "#facc15";
  ctx.textAlign = ahead ? "right" : "left";
  ctx.fillText("Line", x(inset.line) + (ahead ? -3 : 3), top + 16);
  ctx.fillStyle = "#f87171";
  ctx.textAlign = ahead ? "left" : "right";
  ctx.fillText(inset.name.split(" ").at(-1) ?? inset.name, x(inset.attacker) + (ahead ? 3 : -3), top + 16);
  ctx.textAlign = "center";
  // The margin, between the lines.
  const mid = (lineTop + lineBottom) / 2;
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(x(inset.line), mid);
  ctx.lineTo(x(inset.attacker), mid);
  ctx.stroke();
  ctx.fillStyle = "#ffffff";
  ctx.fillText(`${distance(inset.margin)} beyond`, left + boxWidth / 2, top + boxHeight - 8);
  ctx.restore();
}

/**
 * A casual fan's explainer for a VAR decision (docs/audience.md, P5): a still of the pitch from the
 * tracking at the moment the call turned on. The text beside it says only what the still shows.
 */
export function RuleFrame({
  runId,
  insight,
  match,
  layout,
  roster,
}: {
  runId: string;
  insight: Insight;
  match: MatchMeta;
  layout: TrackingLayout;
  roster: Roster;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [shown, setShown] = useState<Still | null>(null);

  useEffect(() => {
    let live = true;
    still(runId, insight, match, layout, roster)
      .then((s) => live && setShown(s))
      .catch(() => live && setShown(null));
    return () => {
      live = false;
    };
  }, [runId, insight, match, layout, roster]);

  useEffect(() => {
    if (canvas.current && shown) draw(canvas.current, shown, match, layout);
  }, [shown, match, layout]);

  if (!shown) return null;
  return (
    <figure className="space-y-1.5">
      <canvas ref={canvas} className="block aspect-111/74 w-full rounded-lg bg-[#2f6b3a]" role="img" aria-label={shown.label} />
      <figcaption className="text-xs text-muted-foreground">{shown.caption}</figcaption>
    </figure>
  );
}
