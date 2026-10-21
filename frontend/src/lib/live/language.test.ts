import { describe, expect, it } from "vitest";

import { inLanguage, localized, untranslated } from "./language";
import { translatedLabel } from "./shortlist";
import { insightFixture } from "./test-fixtures";

const english = { headline: "Adeyani scores", casual: "Kingsferry lead.", analyst: "From 21 m.", plain: "Adeyani scores. Kingsferry lead.", evidence: ["e0391"], facts: [] };
const spanish = { headline: "Marca Adeyani", casual: "Kingsferry se adelanta.", analyst: "Desde 21 m." };

describe("cards in the fan's language", () => {
  it("shows the checked translation once it is there, keeping everything else", () => {
    const card = insightFixture("goal-e0391", { card: english, translations: { es: spanish } });
    const shown = inLanguage(card, "es");
    expect(shown.card).toEqual({ ...english, ...spanish, plain: "Marca Adeyani. Kingsferry se adelanta." });
    expect(shown.card.evidence).toEqual(["e0391"]);
    expect(untranslated(shown, "es")).toBe(false);
  });

  it("keeps the English until a translation is there, and for English readers", () => {
    const card = insightFixture("goal-e0391", { card: english, translations: { es: spanish } });
    expect(inLanguage(card, "fr").card).toEqual(english);
    expect(untranslated(card, "fr")).toBe(true);
    expect(untranslated(insightFixture("x", { card: english }), "es")).toBe(true);
    expect(untranslated(card, "en")).toBe(false);
    const shown = [{ insight: card, from: 1300 }];
    expect(localized(shown, "en")).toBe(shown);
    expect(localized(shown, "es")[0].insight.card.headline).toBe("Marca Adeyani");
  });

  it("tells the producer which languages a card is ready in", () => {
    expect(translatedLabel(insightFixture("x", { translations: { fr: spanish, es: spanish } }))).toBe("Translated: ES, FR");
    expect(translatedLabel(insightFixture("x"))).toBeNull();
  });
});
