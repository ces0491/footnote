// What a fan's settings change (docs/experience.md; docs/audience.md, P6): casual and analyst are
// separate experiences, the fan's club frames everything, and a player in focus adds their line to
// every moment they are in.

import type { Club, Insight, InsightKind, PlayerLine, StateView, TeamStats } from "./contract";
import { NBSP } from "./describe";
import type { Shown } from "./playback";
import type { Metric, Mode } from "./profiles";

// Casual fans get the moments, the rule calls, the spells of play and the corrections; analysts get
// the figures as well.
const CASUAL_KINDS: ReadonlySet<InsightKind> = new Set(["moment", "rule_call", "segment", "recap", "correction"]);

export function forMode(shown: Shown[], mode: Mode): Shown[] {
  return mode === "analyst" ? shown : shown.filter((s) => CASUAL_KINDS.has(s.insight.kind));
}

/**
 * What VAR or a correction did to a card. A card whose facts a correction restated carries the
 * correction's seq as its own: its wording is already the corrected one. Any other flagged card
 * cites something that no longer stands.
 */
export function undone(insight: Insight): "corrected" | "undone" | null {
  if (!insight.flag) return null;
  return insight.seq === insight.flag.seq ? "corrected" : "undone";
}

/** Whether a card is about the player: their name is one of its facts. */
export function involves(insight: Insight, playerName: string): boolean {
  return Object.values(insight.fields).includes(playerName);
}

/** The player's line as an analyst reads it, from the tracking and the pass model. */
export function playerLine(line: PlayerLine | undefined): string[] {
  if (!line) return [];
  const out = [`Passes ${line.completed}/${line.passes}`];
  if (line.difficulty !== null) out.push(`Avg difficulty ${line.difficulty.toFixed(2)}`);
  if (line.hardest !== null) out.push(`Hardest ${line.hardest.toFixed(2)}${line.hardest_minute ? ` (${line.hardest_minute}')` : ""}`);
  if (line.distance_km !== undefined) out.push(`Distance ${line.distance_km.toFixed(1)}${NBSP}km`);
  if (line.top_speed_kmh !== undefined) out.push(`Top speed ${line.top_speed_kmh.toFixed(1)}${NBSP}km/h`);
  return out;
}

const percent = (v: number | null | undefined) => (v === null || v === undefined ? "–" : `${Math.round(v * 100)}%`);

function teamFigure(metric: Metric, stats: TeamStats | undefined): string {
  if (!stats) return "–";
  switch (metric) {
    case "pass_difficulty":
      return stats.pass_difficulty === null || stats.pass_difficulty === undefined ? "–" : stats.pass_difficulty.toFixed(2);
    case "possession":
      return percent(stats.possession);
    case "pass_accuracy":
      return percent(stats.pass_accuracy);
    case "distance":
      return stats.distance_km === null || stats.distance_km === undefined ? "–" : `${stats.distance_km.toFixed(1)}${NBSP}km`;
    case "shots":
      return `${stats.shots} (${stats.on_target} on target)`;
  }
}

function playerFigure(metric: Metric, line: PlayerLine | undefined): string | null {
  if (!line) return null;
  if (metric === "pass_difficulty" && line.difficulty !== null) {
    return `${line.difficulty.toFixed(2)}${line.hardest !== null ? `, hardest ${line.hardest.toFixed(2)}` : ""}`;
  }
  if (metric === "pass_accuracy" && line.passes > 0) return percent(line.completed / line.passes);
  if (metric === "distance" && line.distance_km !== undefined) return `${line.distance_km.toFixed(1)}${NBSP}km`;
  return null;
}

export interface MetricFigures {
  clubs: { club: Club; figure: string }[];
  player: { name: string; figure: string } | null;
}

/** The metric an analyst pins: each club's figure, in the order given, and the player's where it has one. */
export function metricFigures(
  metric: Metric,
  view: StateView,
  clubs: [Club, Club],
  player: { name: string; line: PlayerLine | undefined } | null,
): MetricFigures {
  const own = player ? playerFigure(metric, player.line) : null;
  return {
    clubs: clubs.map((club) => ({ club, figure: teamFigure(metric, view.teams[club.id]) })),
    player: player && own ? { name: player.name, figure: own } : null,
  };
}

/** The two clubs with the fan's own first, when they have one. */
export function ownFirst(home: Club, away: Club, club: string | null): [Club, Club] {
  return club === away.id ? [away, home] : [home, away];
}
