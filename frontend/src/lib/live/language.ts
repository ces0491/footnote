// The language a fan reads the cards in (docs/experience.md, Lucía). The agents write English; the
// agents service has Azure AI Translator render each card in Spanish and French, and code checks
// every figure and name came through before a translation joins the card (src/footnote/agents/
// translator.py). A card whose translation isn't there yet, or failed the check, stays in English,
// unless the viewer has had an earlier wording of the same facts in their language. A card's notes
// about itself go in its language too (`cardNote`); the page around the cards stays in English.

import type { Insight } from "./contract";
import type { Shown } from "./playback";

export const LANGUAGES = { en: "English", es: "Español", fr: "Français" } as const;
export type Language = keyof typeof LANGUAGES;

// The copies made in another language, by the insight they were made from (insights are replaced,
// never changed in place): a page renders every 250 ms, and a component that acts when its insight
// changes, such as the VAR still that fetches its events, must get the same copy each time.
const copies = new WeakMap<Insight, Map<string, Insight>>();

function copy(of: Insight, key: string, make: () => Insight): Insight {
  let made = copies.get(of);
  if (!made) copies.set(of, (made = new Map()));
  let out = made.get(key);
  if (!out) made.set(key, (out = make()));
  return out;
}

/** The card in `lang`, or as it is when that's English or there is no checked translation. */
export function inLanguage(insight: Insight, lang: Language): Insight {
  const t = lang === "en" ? undefined : insight.translations?.[lang];
  if (!t) return insight;
  return copy(insight, lang, () => {
    // As the processor makes the English one: the headline, then the casual line.
    const plain = t.casual ? `${t.headline.replace(/\.$/, "")}. ${t.casual}` : t.headline;
    return { ...insight, card: { ...insight.card, headline: t.headline, casual: t.casual, analyst: t.analyst, plain } };
  });
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
    const insight = copy(s.insight, `${lang} as of version ${before.version}`, () => ({
      ...s.insight,
      card: inLanguage(before, lang).card,
    }));
    return { ...s, insight, lang };
  });
}

/** The `lang` attribute for wording in `lang`: none for English, the page's own language. */
export function langAttribute(lang: Language | undefined): Language | undefined {
  return lang === "en" ? undefined : lang;
}

// What a card says about itself, beside its wording: the processor's flags for a goal VAR took away,
// and the note on a card the data provider corrected. They go in the card's language with it.
const NOTES: Record<string, Record<Exclude<Language, "en">, string>> = {
  "Corrected by the data provider": { es: "Corregido por el proveedor de datos", fr: "Corrigé par le fournisseur de données" },
  "Ruled out by VAR": { es: "Anulado por el VAR", fr: "Annulé par la VAR" },
  "The goal it cites was ruled out by VAR": {
    es: "El gol que cita fue anulado por el VAR",
    fr: "Le but cité a été annulé par la VAR",
  },
};

/** A card's note in the card's language, and that language; a note with no translation stays English. */
export function cardNote(note: string, lang: Language | undefined): { text: string; lang: Language } {
  const translated = lang && lang !== "en" ? NOTES[note]?.[lang] : undefined;
  return translated ? { text: translated, lang: lang! } : { text: note, lang: "en" };
}
