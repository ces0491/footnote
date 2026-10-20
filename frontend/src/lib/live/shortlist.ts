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

/** The strongest live insights current at `now` (none can air once killed or withdrawn). */
export function shortlist(insights: Insight[], now: MatchTime | null, size = SHORTLIST_SIZE): Insight[] {
  return insights
    .filter((i) => i.live && i.kind !== "correction" && !i.flag && i.status !== "killed" && i.status !== "withdrawn")
    .filter((i) => !now || (atOrBefore(i.at, now) && atOrBefore(now, i.until)))
    .sort((a, b) => b.rank - a.rank || b.seq - a.seq)
    .slice(0, size);
}

/** Corrections, and the insights they or VAR undid, newest first. */
export function corrections(insights: Insight[]): Insight[] {
  return insights.filter((i) => i.live && (i.kind === "correction" || i.flag !== null)).sort((a, b) => b.seq - a.seq);
}

/** Where an insight's wording came from, in a few words; `agent_note` says why a template stands. */
export function provenanceLabel(insight: Insight): string {
  if (insight.source === "agent") return insight.provenance.cached ? "Agent, reused" : "Agent";
  if (insight.agent_state === "pending" || insight.agent_state === "drafting") return "Template · agent drafting";
  if (insight.agent_state === "fallback") return "Template · agent fell back";
  return "Template";
}
