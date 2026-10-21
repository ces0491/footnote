// The language a fan reads the cards in (docs/experience.md, Lucía). The agents write English; the
// agents service has Azure AI Translator render each card in Spanish and French, and code checks
// every figure and name came through before a translation joins the card (src/footnote/agents/
// translator.py). A card whose translation isn't there yet, or failed the check, stays in English,
// unless the viewer has had an earlier wording of the same facts in their language. The page around
// the cards stays in English.

import type { Insight } from "./contract";
import type { Shown } from "./playback";

export const LANGUAGES = { en: "English", es: "Español", fr: "Français" } as const;
export type Language = keyof typeof LANGUAGES;

/** The card in `lang`, or as it is when that's English or there is no checked translation. */
export function inLanguage(insight: Insight, lang: Language): Insight {
  const t = lang === "en" ? undefined : insight.translations?.[lang];
  if (!t) return insight;
  // As the processor makes the English one: the headline, then the casual line.
  const plain = t.casual ? `${t.headline.replace(/\.$/, "")}. ${t.casual}` : t.headline;
  return { ...insight, card: { ...insight.card, headline: t.headline, casual: t.casual, analyst: t.analyst, plain } };
}

/**
 * The cards in `lang`, each marked with the language its wording is in. A state with no translation
 * yet keeps the translated card of the latest earlier state the viewer has had with the same facts
 * (`seq`), under the current state's status, flag and the rest: an agent's or the producer's
 * rewording, or a change of status, doesn't send a card back to English while its own translation is
 * on its way. A state a correction restated has new facts, so it shows the English until it is
 * translated.
 */
export function localized(shown: Shown[], lang: Language): Shown[] {
  return shown.map((s) => {
    if (lang === "en") return { ...s, lang };
    if (s.insight.translations?.[lang]) return { ...s, insight: inLanguage(s.insight, lang), lang };
    const before = s.earlier?.findLast((e) => e.seq === s.insight.seq && e.translations?.[lang]);
    if (!before) return { ...s, lang: "en" };
    return { ...s, insight: { ...s.insight, card: inLanguage(before, lang).card }, lang };
  });
}

/** The `lang` attribute for wording in `lang`: none for English, the page's own language. */
export function langAttribute(lang: Language | undefined): Language | undefined {
  return lang === "en" ? undefined : lang;
}
