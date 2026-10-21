import { describe, expect, it } from "vitest";

import { catchUpOf, keyMoments } from "./catch-up";
import type { Insight } from "./contract";
import type { Shown } from "./playback";
import { insightFixture } from "./test-fixtures";

/** A card kept as history, at `minute` of the first half or, past 45, the second. */
function history(id: string, minute: number, overrides: Partial<Insight> = {}): Shown {
  const period = minute > 45 ? 2 : 1;
  const at = { period, t: (minute - (period === 2 ? 45 : 0)) * 60 - 30, minute, added_minute: null };
  return { insight: insightFixture(id, { live: false, at, ...overrides }), from: 1290 };
}

function headline(text: string): Partial<Insight> {
  return { card: { headline: text, casual: "", analyst: "", plain: "", evidence: [], facts: [] } };
}

const pressure = { kind: "segment" as const, topic: "pressure", ...headline("Saltmarsh pinning Kingsferry back") };

describe("catch-up", () => {
  it("finds the run's catch-up among the cards that reached the viewer", () => {
    const goal = { insight: insightFixture("goal-e1029"), from: 1300 };
    const catchUp = { insight: insightFixture("catchup", { kind: "recap", topic: "catch_up", placement: "side_panel" }), from: 1290, lang: "es" as const };
    expect(catchUpOf([goal, catchUp])).toBe(catchUp);
    expect(catchUpOf([goal])).toBeNull();
  });

  it("lists the moments before the start in match order, with spells in a row as one", () => {
    const moments = keyMoments(
      [
        history("goal-e1029", 52, headline("Teo Varlan scores")),
        history("pressure-1", 39, pressure),
        history("goal-e0391", 23, headline("Femi Adeyani scores")),
        history("pressure-2", 44, pressure),
        history("var-e0534", 33, { kind: "rule_call", topic: "var_decision", ...headline("VAR: No goal") }),
      ],
      "en",
    );
    expect(moments.map((m) => `${m.minutes} ${m.label}`)).toEqual([
      "23' Femi Adeyani scores",
      "33' VAR: No goal",
      "39'–44' Saltmarsh pinning Kingsferry back",
      "52' Teo Varlan scores",
    ]);
  });

  it("keeps spells either side of half-time apart", () => {
    const moments = keyMoments([history("pressure-sal-1-2440", 44, pressure), history("pressure-sal-2-1", 49, pressure)], "en");
    expect(moments.map((m) => `${m.minutes} ${m.label}`)).toEqual([
      "44' Saltmarsh pinning Kingsferry back",
      "49' Saltmarsh pinning Kingsferry back",
    ]);
  });

  it("lists them in the viewer's language, in English where a card has no translation yet", () => {
    const goal = history("goal-e0391", 23, {
      ...headline("Femi Adeyani scores"),
      translations: { es: { headline: "Femi Adeyani anota", casual: "", analyst: "" } },
    });
    const moments = keyMoments([goal, history("pressure-sal-1-318", 9, pressure)], "es");
    expect(moments.map((m) => [m.label, m.lang])).toEqual([
      ["Saltmarsh pinning Kingsferry back", "en"],
      ["Femi Adeyani anota", "es"],
    ]);
  });

  it("leaves out live cards, stats, started checks, spells of control and what VAR undid", () => {
    const flag = { reason: "Ruled out by VAR", event_id: "e0534", version: 1, seq: 535 };
    const moments = keyMoments(
      [
        history("goal-e0532", 31, { flag, seq: 533 }), // undone: its decision tells it
        history("var-e0533", 31, { kind: "rule_call", topic: "var_started" }),
        history("keypass-e0387", 23, { kind: "stat", topic: "key_pass" }),
        history("control-sal-1-0", 7, { kind: "segment", topic: "control" }),
        { insight: insightFixture("goal-e1586", { live: true }), from: 1400 },
        history("goal-e1586", 81, { flag: { ...flag, seq: 1620 }, seq: 1620 }), // corrected: it stands
      ],
      "en",
    );
    expect(moments.map((m) => m.key)).toEqual(["goal-e1586"]);
  });
});
