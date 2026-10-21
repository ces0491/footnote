// What a viewer joining a match already under way missed (docs/experience.md, "Catch-up";
// docs/audience.md, P7). A replay that starts mid-match carries a catch-up card, found at the end of
// its backfill and worded by the recap agent, which leaves the score out: the viewer asks for it.
// Under it go the moments before the replay's start, from the cards kept as history for catch-up.

import type { Insight, InsightKind } from "./contract";
import { undone } from "./fan";
import type { Shown } from "./playback";
import { minuteLabel } from "./timeline";

export const CATCH_UP_TOPIC = "catch_up";

/** The catch-up card among the cards airing at the viewer's playback, if the run has one. */
export function catchUpOf(cards: Shown[]): Insight | null {
  return cards.find((s) => s.insight.topic === CATCH_UP_TOPIC)?.insight ?? null;
}

// What a catch-up lists: what changed the match, the spells of pressure or chaos, and the
// provider's corrections. A VAR check that started is told by its decision, and spells of control,
// a dominant side's ordinary state, by the catch-up's own words.
const KINDS: ReadonlySet<InsightKind> = new Set(["moment", "rule_call", "segment", "correction"]);
const UNLISTED: ReadonlySet<string> = new Set(["var_started", "control"]);

export interface KeyMoment {
  key: string;
  minutes: string; // "23'", or "39'–49'" for spells of one state in a row
  label: string;
}

function minuteOf(insight: Insight): string {
  return minuteLabel(insight.at.minute ?? 0, insight.at.added_minute ?? null);
}

/**
 * The moments before the replay's start, in match order, each as it stood at the viewer's playback
 * (`shown` is lib/live/playback.ts's insightsAt). Spells of the same state in a row make one entry; a
 * moment VAR undid is left out, since its decision tells it.
 */
export function keyMoments(shown: Shown[]): KeyMoment[] {
  const told = shown
    .map((s) => s.insight)
    .filter((i) => !i.live && KINDS.has(i.kind) && !UNLISTED.has(i.topic) && undone(i) !== "undone")
    .sort((a, b) => a.at.period - b.at.period || a.at.t - b.at.t);
  const out: KeyMoment[] = [];
  let spell: { first: string; headline: string } | null = null;
  for (const insight of told) {
    const minute = minuteOf(insight);
    if (insight.kind === "segment" && spell?.headline === insight.card.headline) {
      out[out.length - 1] = { ...out[out.length - 1], minutes: `${spell.first}–${minute}` };
      continue;
    }
    spell = insight.kind === "segment" ? { first: minute, headline: insight.card.headline } : null;
    out.push({ key: insight.insight_id, minutes: minute, label: insight.card.headline });
  }
  return out;
}
