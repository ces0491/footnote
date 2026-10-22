import { describe, expect, it } from "vitest";

import type { Club } from "@/lib/live/contract";
import { insightFixture } from "@/lib/live/test-fixtures";

import { clubOf, kindOf } from "./card-kind";

const home = { id: "sal", code: "SAL", name: "Saltmarsh Rovers", short_name: "Saltmarsh", colours: ["#1F7A6D", "#F4F1E8"], formation: "4-2-3-1" } as Club;
const away = { id: "kin", code: "KIN", name: "Kingsferry Athletic", short_name: "Kingsferry", colours: ["#1B2A4A", "#E8A33D"], formation: "4-4-2" } as Club;

describe("clubOf", () => {
  it("finds the club a card is about from its facts: the scorer's side, the side on top", () => {
    const goal = insightFixture("goal-e0391", { fields: { "moment.club": "Kingsferry", "moment.other_club": "Saltmarsh" } });
    expect(clubOf(goal, home, away)).toBe(away);
    const spell = insightFixture("pressure-sal-1-2440", { kind: "segment", topic: "pressure", fields: { "segment.club": "Saltmarsh" } });
    expect(clubOf(spell, home, away)).toBe(home);
  });

  it("leaves a card about no one club to its kind's colour", () => {
    const check = insightFixture("var-e0534", { kind: "rule_call", topic: "var_decision", fields: { "moment.subject": "Marco Dellow" } });
    expect(clubOf(check, home, away)).toBeNull();
  });
});

describe("kindOf", () => {
  it("knows a card by its topic, and by its kind for a topic it hasn't met", () => {
    expect(kindOf(insightFixture("var-e0534", { kind: "rule_call", topic: "var_decision" })).tone).toBe("var");
    expect(kindOf(insightFixture("correction-e1586", { kind: "correction", topic: "correction" })).tone).toBe("amend");
    expect(kindOf(insightFixture("new-1", { kind: "segment", topic: "something_new" })).tone).toBe("plain");
  });
});
