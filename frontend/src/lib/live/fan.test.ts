import { describe, expect, it } from "vitest";

import type { Club, StateView, TeamStats } from "./contract";
import { forMode, involves, metricFigures, ownFirst, playerLine, undone } from "./fan";
import { insightFixture } from "./test-fixtures";

const club = (id: string): Club => ({ id, code: id.toUpperCase(), name: id, short_name: id, colours: ["#000", "#fff"], formation: "4-4-2" });
const sal = club("sal");
const kin = club("kin");

const stats = (overrides: Partial<TeamStats>): TeamStats => ({
  shots: 4,
  on_target: 2,
  passes: 300,
  passes_completed: 260,
  corners: 3,
  fouls: 5,
  offsides: 1,
  yellow_cards: 0,
  red_cards: 0,
  pass_accuracy: 0.867,
  possession: 0.62,
  pass_difficulty: 0.412,
  distance_km: 58.25,
  ...overrides,
});

describe("fan settings", () => {
  const goal = { insight: insightFixture("goal"), from: 10 };
  const pass = { insight: insightFixture("hardpass", { kind: "stat", placement: "side_panel", duration: null }), from: 9 };
  const spell = { insight: insightFixture("pressure", { kind: "segment", placement: "side_panel", duration: null }), from: 8 };

  it("gives casual fans the moments and spells, and analysts the figures as well", () => {
    expect(forMode([goal, pass, spell], "casual").map((s) => s.insight.insight_id)).toEqual(["goal", "pressure"]);
    expect(forMode([goal, pass, spell], "analyst")).toHaveLength(3);
  });

  it("tells a card a correction restated from one VAR or a correction undid", () => {
    const flag = { reason: "The provider amended the goal this cites", event_id: "e1620", version: 2, seq: 1620 };
    expect(undone(insightFixture("goal-e1586", { seq: 1620, flag }))).toBe("corrected");
    expect(undone(insightFixture("keypass-e1584", { seq: 1586, flag }))).toBe("undone");
    expect(undone(insightFixture("goal-e0391"))).toBeNull();
  });

  it("finds the player in a card's facts", () => {
    const card = insightFixture("keypass", { fields: { "moment.passer": "Teo Varlan", "moment.minute": "23'" } });
    expect(involves(card, "Teo Varlan")).toBe(true);
    expect(involves(card, "Marco Dellow")).toBe(false);
  });

  it("reads the player's line and the pinned metric, the fan's club first", () => {
    const line = { player_id: "sal-10", passes: 46, completed: 41, difficulty: 0.48, hardest: 0.86, hardest_minute: 31, distance_km: 6.2, top_speed_kmh: 31.4 };
    expect(playerLine(line)).toEqual([
      "Passes 41/46",
      "Avg difficulty 0.48",
      "Hardest 0.86 (31')",
      "Distance 6.2\u00a0km",
      "Top speed 31.4\u00a0km/h",
    ]);
    const view: StateView = { seq: 1, phase: "first_half", clock: null, score: { home: 0, away: 1 }, teams: { sal: stats({}), kin: stats({ pass_difficulty: 0.35, possession: 0.38 }) }, key_events: [] };
    const figures = metricFigures("pass_difficulty", view, ownFirst(sal, kin, "kin"), { name: "Teo Varlan", line });
    expect(figures.clubs.map((c) => [c.club.id, c.figure])).toEqual([["kin", "0.35"], ["sal", "0.41"]]);
    expect(figures.player).toEqual({ name: "Teo Varlan", figure: "0.48, hardest 0.86" });
    expect(metricFigures("possession", view, [sal, kin], null).clubs.map((c) => c.figure)).toEqual(["62%", "38%"]);
  });
});
