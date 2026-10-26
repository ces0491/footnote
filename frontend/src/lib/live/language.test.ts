import { describe, expect, it } from "vitest";

import type { Insight, InsightMessage } from "./contract";
import { cardNote, inLanguage, langAttribute, localized } from "./language";
import { insightsAt } from "./playback";
import { initialRunViewState, runReducer } from "./run-reducer";
import { translatedLabel } from "./shortlist";
import { baseSnapshot, eventPush, insightFixture, runFixture } from "./test-fixtures";

const english = { headline: "Adeyani scores", casual: "Kingsferry lead.", analyst: "From 21 m.", plain: "Adeyani scores. Kingsferry lead.", evidence: ["e0391"], facts: [] };
const spanish = { headline: "Marca Adeyani", casual: "Kingsferry se adelanta.", analyst: "Desde 21 m." };

describe("cards in the fan's language", () => {
  it("shows the checked translation once it is there, keeping everything else", () => {
    const card = insightFixture("goal-e0391", { card: english, translations: { es: spanish } });
    const shown = inLanguage(card, "es");
    expect(shown.card).toEqual({ ...english, ...spanish, plain: "Marca Adeyani. Kingsferry se adelanta." });
    expect(shown.card.evidence).toEqual(["e0391"]);
  });

  it("gives the same copy of a card each time, so a page rendering again doesn't make it look new", () => {
    // The VAR still fetches its events when its card changes, and the page renders every 250 ms.
    const card = insightFixture("var-e1456", { card: english, translations: { es: spanish } });
    expect(inLanguage(card, "es")).toBe(inLanguage(card, "es"));
    const redraft = insightFixture("var-e1456", { card: { ...english, casual: "No penalty." }, source: "agent", version: 2 });
    const shown = [{ insight: redraft, from: 1400, earlier: [card] }];
    expect(localized(shown, "es")[0].insight).toBe(localized(shown, "es")[0].insight);
    // A new state of the card is a new card, in every language.
    const translated = { ...redraft, translations: { es: spanish } };
    expect(inLanguage(translated, "es")).not.toBe(inLanguage(card, "es"));
  });

  it("keeps the English until a translation is there, and says which language each card is in", () => {
    const card = insightFixture("goal-e0391", { card: english, translations: { es: spanish } });
    expect(inLanguage(card, "fr").card).toEqual(english);
    const shown = [{ insight: card, from: 1300 }];
    expect(localized(shown, "en")).toEqual([{ insight: card, from: 1300, lang: "en" }]);
    expect(localized(shown, "es")[0]).toMatchObject({ insight: { card: { headline: "Marca Adeyani" } }, lang: "es" });
    expect(localized(shown, "fr")[0]).toEqual({ insight: card, from: 1300, lang: "en" });
  });

  it("keeps an earlier translation of the same facts while a rewording's own is on its way", () => {
    const template = insightFixture("chaos-2-1108", { card: english, translations: { es: spanish } });
    const redraft = insightFixture("chaos-2-1108", {
      card: { ...english, casual: "Kingsferry are ahead." },
      source: "agent",
      version: 2,
      status_by: "producer",
    });
    const [shown] = localized([{ insight: redraft, from: 1300, earlier: [template] }], "es");
    expect(shown.lang).toBe("es");
    expect(shown.insight.card.casual).toBe(spanish.casual);
    expect(shown.insight).toMatchObject({ source: "agent", version: 2, status_by: "producer" });
  });

  it("shows a card a correction restated in English until its new wording is translated", () => {
    const flag = { reason: "The data provider amended the goal this cites", event_id: "e1619", version: 2, seq: 1620 };
    const before = insightFixture("goal-e1586", { seq: 1587, card: english, translations: { es: spanish } });
    const restated = insightFixture("goal-e1586", { seq: 1620, flag, card: { ...english, headline: "Femi Adeyani scores" } });
    const [shown] = localized([{ insight: restated, from: 1400, earlier: [before] }], "es");
    expect(shown.lang).toBe("en");
    expect(shown.insight).toBe(restated);
  });

  it("doesn't go back to English between a translated template and the agent's translated draft", () => {
    // As the 67', 71' and 75' cards came for Lucía: the template, its translation, the agent's draft,
    // and the draft's translation, each a state of its own.
    const run = runFixture();
    const template = insightFixture("chaos-2-1108", { shown_seq: 15, card: english, agent_state: "pending" });
    const draft = { ...english, casual: "Kingsferry are ahead." };
    const states: Insight[] = [
      template,
      { ...template, translations: { es: spanish }, updated_at: "2026-10-20T12:00:02Z" },
      { ...template, source: "agent", version: 2, agent_state: "done", card: draft, updated_at: "2026-10-20T12:00:15Z" },
      {
        ...template,
        source: "agent",
        version: 2,
        agent_state: "done",
        card: draft,
        translations: { es: { ...spanish, casual: "Kingsferry va por delante." } },
        updated_at: "2026-10-20T12:00:20Z",
      },
    ];
    let state = runReducer(initialRunViewState, {
      kind: "resynced",
      pushes: [baseSnapshot(10), ...Array.from({ length: 10 }, (_, i) => eventPush(11 + i))],
      ended: null,
      backfillSeq: 10,
      insights: [],
      insightRev: 0,
    });
    const seen: string[] = [];
    states.forEach((insight, i) => {
      const message: InsightMessage = { type: "insight", run_id: run.run_id, rev: i + 1, insight };
      state = runReducer(state, { kind: "push", message });
      const [shown] = localized(insightsAt(state, run, 1310), "es");
      seen.push(`${shown.lang}: ${shown.insight.card.casual}`);
    });
    expect(seen).toEqual(["en: Kingsferry lead.", "es: Kingsferry se adelanta.", "es: Kingsferry se adelanta.", "es: Kingsferry va por delante."]);
  });

  it("marks Spanish and French wording for screen readers, and leaves English to the page", () => {
    expect(langAttribute("es")).toBe("es");
    expect(langAttribute("fr")).toBe("fr");
    expect(langAttribute("en")).toBeUndefined();
    expect(langAttribute(undefined)).toBeUndefined();
  });

  it("gives a card's notes in the card's language, and an unknown one in English", () => {
    expect(cardNote("Corrected by the data provider", "es")).toEqual({ text: "Corregido por el proveedor de datos", lang: "es" });
    expect(cardNote("Ruled out by VAR", "fr")).toEqual({ text: "Annulé par la VAR", lang: "fr" });
    expect(cardNote("Ruled out by VAR", "en")).toEqual({ text: "Ruled out by VAR", lang: "en" });
    expect(cardNote("Something new", "es")).toEqual({ text: "Something new", lang: "en" });
  });

  it("tells the producer which languages a card is ready in", () => {
    expect(translatedLabel(insightFixture("x", { translations: { fr: spanish, es: spanish } }))).toBe("Translated: ES, FR");
    expect(translatedLabel(insightFixture("x"))).toBeNull();
  });
});
