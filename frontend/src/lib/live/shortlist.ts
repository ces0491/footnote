// The producer's shortlist (docs/experience.md): the strongest few insights still current, each
// with its reason. Ranks come from the processor (src/footnote/insights/moments.py); this only picks
// and orders. Corrections, and insights VAR or a correction undid, are kept apart: they need the
// producer's attention rather than a place in the running order.

import type { Insight, MatchTime } from "./contract";

export const SHORTLIST_SIZE = 3;

/** Whether match time `a` is at or before `b`. */
export function atOrBefore(a: MatchTime, b: MatchTime): boolean {
  return a.period < b.period || (a.period === b.period && a.t <= b.t);
}

/** Whether an insight is current at `now`: its moment has come and its time on screen hasn't passed. */
function current(insight: Insight, now: MatchTime | null): boolean {
  return !now || (atOrBefore(insight.at, now) && atOrBefore(now, insight.until));
}

const offAirStatus = (insight: Insight) => insight.status === "killed" || insight.status === "withdrawn";

/** The strongest live insights current at `now`, leaving out those killed or withdrawn (`offAir`). */
export function shortlist(insights: Insight[], now: MatchTime | null, size = SHORTLIST_SIZE): Insight[] {
  return insights
    .filter((i) => i.live && i.kind !== "correction" && !i.flag && !offAirStatus(i) && current(i, now))
    .sort((a, b) => b.rank - a.rank || b.seq - a.seq)
    .slice(0, size);
}

/** Insights the producer killed or withdrew that are still current at `now`, newest first: one can be
 * approved again while its moment lasts. Those VAR or a correction undid are under `corrections`. */
export function offAir(insights: Insight[], now: MatchTime | null): Insight[] {
  return insights
    .filter((i) => i.live && i.kind !== "correction" && !i.flag && offAirStatus(i) && current(i, now))
    .sort((a, b) => b.seq - a.seq);
}

/** Corrections, and the insights they or VAR undid, newest first. */
export function corrections(insights: Insight[]): Insight[] {
  return insights.filter((i) => i.live && (i.kind === "correction" || i.flag !== null)).sort((a, b) => b.seq - a.seq);
}

/**
 * What a card's claims rest on: the events it links to, or for a player tag, the tracking (sprints
 * and distances come from player positions, not from any event). Null for a card with neither.
 */
export function evidenceSource(insight: Insight): "events" | "tracking" | null {
  if (insight.card.evidence.length > 0) return "events";
  return insight.kind === "player_tag" ? "tracking" : null;
}

/** Where an insight's wording came from, in a few words; `agent_note` says why an agent's draft didn't land. */
export function provenanceLabel(insight: Insight): string {
  if (insight.agent_state === "pending" || insight.agent_state === "drafting") {
    return insight.source === "template" ? "Template · agent drafting" : "Agent redrafting";
  }
  if (insight.source === "producer") return "Edited by the producer";
  if (insight.source === "agent") return insight.provenance.cached ? "Agent, reused" : "Agent";
  if (insight.agent_state === "fallback") return "Template · agent fell back";
  return "Template";
}

/** The languages this version of the card is ready in for fans, or null while there are none. */
export function translatedLabel(insight: Insight): string | null {
  const ready = Object.keys(insight.translations ?? {}).sort();
  return ready.length ? `Translated: ${ready.map((lang) => lang.toUpperCase()).join(", ")}` : null;
}

/** Whether an insight airs, and who decided, in a few words. */
export function statusLabel(insight: Insight): string {
  switch (insight.status) {
    case "approved":
      return insight.status_by === "auto" ? "Approved automatically" : "Approved";
    case "drafted":
      return insight.status_by === "correction" ? "Corrected: needs approval again" : "Waiting for approval";
    case "withdrawn":
      return "Withdrawn";
    case "killed":
      return "Killed";
  }
}
