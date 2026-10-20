// A card's wording with its placeholders, as src/footnote/insights/draft.py writes it: `{fact.key}`
// where each figure goes, filled in by code. The console edits drafts in this form; the producer's
// desk checks an edit before anyone sees it, so this is only for showing one.

import type { Draft, Sentence } from "./contract";

const PLACEHOLDER = /\{([A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)+)\}/g;

/** The fact keys a text's placeholders name, in order. */
export function placeholders(text: string): string[] {
  return [...text.matchAll(PLACEHOLDER)].map((m) => m[1]);
}

/** A text with each placeholder filled from `fields`; an unknown key stays as written. */
export function fill(text: string, fields: Record<string, string>): string {
  return text.replace(PLACEHOLDER, (whole, key: string) => fields[key] ?? whole);
}

/** Sentences as one block of text for editing: one sentence a line. */
export function asLines(sentences: Sentence[]): string {
  return sentences.map((s) => s.text).join("\n");
}

/**
 * Edited lines back into sentences. A line keeps the events its sentence cited when it stands where
 * that sentence stood; a new line cites none, so it has to use a fact.
 */
export function fromLines(text: string, before: Sentence[]): Sentence[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, i) => ({ text: line, events: before[i]?.events ?? [] }));
}

/** The draft an edit makes of `draft`: a new headline and lines. */
export function edited(draft: Draft, headline: string, casual: string, analyst: string): Draft {
  return {
    headline: headline.trim(),
    casual: fromLines(casual, draft.casual),
    analyst: fromLines(analyst, draft.analyst),
  };
}
