// Fixtures shared by the tests beside this file. Nothing in the app imports it.

import type { Insight } from "./contract";

export function insightFixture(id: string, overrides: Partial<Insight> = {}): Insight {
  return {
    insight_id: id,
    seq: 392,
    kind: "moment",
    topic: "goal",
    at: { period: 1, t: 1357.25, minute: 23, added_minute: null },
    until: { period: 1, t: 1657.25 },
    rank: 0.95,
    reason: "Goal: against the run of play",
    evidence: ["e0391"],
    placement: "lower_third",
    hold: null,
    corrects: null,
    live: true,
    flag: null,
    status: "drafted",
    agent_state: "pending",
    agent_note: null,
    version: 1,
    source: "template",
    card: { headline: "Femi Adeyani scores", casual: "", analyst: "", plain: "", evidence: ["e0391"], facts: [] },
    provenance: { source: "template", template: "goal" },
    created_at: "2026-10-20T12:00:00Z",
    updated_at: "2026-10-20T12:00:00Z",
    ...overrides,
  };
}
