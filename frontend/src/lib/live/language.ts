// The language a fan reads the cards in (docs/experience.md, Lucía). The agents write English; the
// agents service has Azure AI Translator render each card in Spanish and French, and code checks
// every figure and name came through before a translation joins the card (src/footnote/agents/
// translator.py). A card whose translation isn't there yet, or failed the check, stays in English.
// The page around the cards stays in English.

import type { Insight } from "./contract";
import type { Shown } from "./playback";

export const LANGUAGES = { en: "English", es: "Español", fr: "Français" } as const;
export type Language = keyof typeof LANGUAGES;

/** Whether the card has no checked translation into `lang` yet: the viewer reads the English. */
export function untranslated(insight: Insight, lang: Language): boolean {
  return lang !== "en" && !insight.translations?.[lang];
}

/** The card in `lang`, or as it is when that's English or there is no checked translation. */
export function inLanguage(insight: Insight, lang: Language): Insight {
  const t = lang === "en" ? undefined : insight.translations?.[lang];
  if (!t) return insight;
  // As the processor makes the English one: the headline, then the casual line.
  const plain = t.casual ? `${t.headline.replace(/\.$/, "")}. ${t.casual}` : t.headline;
  return { ...insight, card: { ...insight.card, headline: t.headline, casual: t.casual, analyst: t.analyst, plain } };
}

export function localized(shown: Shown[], lang: Language): Shown[] {
  return lang === "en" ? shown : shown.map((s) => ({ ...s, insight: inLanguage(s.insight, lang) }));
}
