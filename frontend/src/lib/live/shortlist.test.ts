import { describe, expect, it } from "vitest";

import { insightFixture } from "./test-fixtures";
import { corrections, provenanceLabel, shortlist } from "./shortlist";

describe("shortlist", () => {
  const goal = insightFixture("goal-e0391", { rank: 0.95 });
  const pass = insightFixture("keypass-e0387", { rank: 0.53, kind: "stat" });
  const sprint = insightFixture("sprint", { rank: 0.44, kind: "player_tag", at: { period: 1, t: 700 }, until: { period: 1, t: 820 } });
  const history = insightFixture("goal-old", { rank: 0.99, live: false });
  const ruledOut = insightFixture("goal-e0532", { rank: 0.85, flag: { reason: "Ruled out by VAR", event_id: "e0534", version: 1, seq: 535 } });
  const all = [pass, history, goal, sprint, ruledOut];

  it("ranks the live, current, unflagged insights", () => {
    const now = { period: 1, t: 1400 };
    expect(shortlist(all, now).map((i) => i.insight_id)).toEqual(["goal-e0391", "keypass-e0387"]); // the sprint is stale
    expect(shortlist(all, { period: 2, t: 10 })).toEqual([]); // nothing carries over the break
  });

  it("keeps corrections and what they undid apart", () => {
    const notice = insightFixture("correction-e1586-v2", { kind: "correction", seq: 1620 });
    expect(corrections([...all, notice]).map((i) => i.insight_id)).toEqual(["correction-e1586-v2", "goal-e0532"]);
  });

  it("says where the wording came from", () => {
    expect(provenanceLabel(goal)).toBe("Template · agent drafting");
    expect(provenanceLabel({ ...goal, agent_state: "fallback" })).toBe("Template · agent fell back");
    expect(provenanceLabel({ ...goal, source: "agent", provenance: { source: "agent", cached: true } })).toBe("Agent, reused");
  });
});
