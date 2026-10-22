// One line per key event for the match ticker, filled from the event's own fields. Templates only:
// a line says what the event records and nothing more.

import type { FeedEvent, MatchMeta, Player, Tag } from "./contract";
import { minuteLabel } from "./timeline";

// Between a figure and its unit, so a line never wraps between them.
export const NBSP = "\u00a0";

export interface Roster {
  player(id: unknown): Player | undefined;
  clubName(id: unknown): string;
}

export function roster(match: MatchMeta): Roster {
  const players = new Map<string, Player>();
  for (const lineup of match.lineups) {
    for (const p of [...lineup.starters, ...lineup.bench]) players.set(p.player_id, p);
  }
  const clubs = new Map([match.home, match.away].map((c) => [c.id, c.short_name]));
  return {
    player: (id) => (typeof id === "string" ? players.get(id) : undefined),
    clubName: (id) => (typeof id === "string" ? (clubs.get(id) ?? id) : ""),
  };
}

const SHOT_OUTCOME: Record<string, string> = {
  goal: "scores",
  saved: "saved",
  blocked: "blocked",
  off_target: "off target",
};

const CARD: Record<string, string> = { yellow: "Yellow card", second_yellow: "Second yellow, sent off", red: "Red card" };

const VAR_DECISION: Record<string, string> = {
  goal: "goal stands",
  no_goal: "no goal",
  penalty: "penalty",
  no_penalty: "no penalty",
};

function name(r: Roster, id: unknown): string {
  return r.player(id)?.name ?? "Unknown player";
}

export type EventTone = "goal" | "var" | "card" | "correction" | "period" | "plain" | "sprint" | "distance";

export interface EventLine {
  text: string;
  tone: EventTone;
}

export function describe(event: FeedEvent, r: Roster): EventLine {
  const club = r.clubName(event.team_id);
  switch (event.type) {
    case "goal":
      return event.own_goal
        ? { text: `Goal, ${club}: own goal by ${name(r, event.player_id)}`, tone: "goal" }
        : { text: `Goal, ${club}: ${name(r, event.player_id)}`, tone: "goal" };
    case "shot": {
      const outcome = SHOT_OUTCOME[String(event.outcome)] ?? event.outcome;
      const speed = typeof event.speed_kmh === "number" ? `, ${Math.round(event.speed_kmh)}${NBSP}km/h` : "";
      return { text: `${name(r, event.player_id)} (${club}) shoots: ${outcome}${speed}`, tone: "plain" };
    }
    case "var_check": {
      const subject = `${String(event.incident)} by ${name(r, event.subject_id)}`;
      if (event.status === "started") return { text: `VAR checking the ${String(event.check)} for ${subject}`, tone: "var" };
      const decision = VAR_DECISION[String(event.decision)] ?? String(event.decision);
      return { text: `VAR: ${decision}${event.overturned ? ", decision overturned" : ""}`, tone: "var" };
    }
    case "card":
      return { text: `${CARD[String(event.card)] ?? "Card"}: ${name(r, event.player_id)} (${club})`, tone: "card" };
    case "substitution":
      return { text: `${club} substitution: ${name(r, event.player_on_id)} on for ${name(r, event.player_off_id)}`, tone: "plain" };
    case "offside":
      return { text: `${name(r, event.player_id)} (${club}) caught offside`, tone: "plain" };
    case "injury":
      return { text: `${name(r, event.player_id)} (${club}) down injured`, tone: "plain" };
    case "added_time":
      return { text: `${String(event.minutes)} minutes added`, tone: "period" };
    case "period_start":
      return { text: event.period === 1 ? "Kick-off" : "Second half under way", tone: "period" };
    case "period_end":
      return { text: event.period === 1 ? "Half-time" : "Final whistle", tone: "period" };
    case "match_end":
      return { text: "Full time", tone: "period" };
    case "amendment":
      return { text: correction(event, r), tone: "correction" };
    case "pass": {
      const to = event.recipient_id ? ` to ${name(r, event.recipient_id)}` : "";
      return { text: `${name(r, event.player_id)} (${club}) passes${to}: ${String(event.outcome).replaceAll("_", " ")}`, tone: "plain" };
    }
    default: {
      // Events the ticker doesn't list but an insight's evidence can: carries, duels, recoveries.
      const kind = event.type.replaceAll("_", " ");
      return { text: event.player_id ? `${name(r, event.player_id)} (${club}): ${kind}` : kind, tone: "plain" };
    }
  }
}

export interface TickerLine extends EventLine {
  key: string;
  minute: number;
  addedMinute: number | null;
  correctedAt: string | null; // the minute the provider amended the event, once the list has the amendment
  ruledOutAt: string | null; // the minute VAR ruled the goal out, once the list has the decision
}

/**
 * Key events in feed order, with each tag placed before the first event that comes after it in the
 * match. Events keep their own order: a correction carries the clock of the whistle before it. An
 * event the provider amended later in the list keeps its line as it was first recorded, marked with
 * when it was corrected.
 */
export function tickerLines(events: FeedEvent[], tags: Tag[], r: Roster): TickerLine[] {
  // An amendment carries the ID of the event it amends; the latest one for each event.
  const amendments = new Map<string, FeedEvent>();
  for (const event of events) if (event.type === "amendment") amendments.set(event.event_id, event);
  const correctedAt = (event: FeedEvent) => {
    const amendment = amendments.get(event.event_id);
    return amendment && amendment.seq > event.seq ? minuteLabel(amendment.minute, amendment.added_minute) : null;
  };
  // A goal VAR ruled out keeps its line too, marked: the decision names the goal it took away.
  const decisions = new Map<string, FeedEvent>();
  for (const event of events) {
    if (event.type === "var_check" && event.decision === "no_goal" && typeof event.goal_event_id === "string") {
      decisions.set(event.goal_event_id, event);
    }
  }
  const ruledOutAt = (event: FeedEvent) => {
    const decision = event.type === "goal" ? decisions.get(event.event_id) : undefined;
    return decision && decision.seq > event.seq ? minuteLabel(decision.minute, decision.added_minute) : null;
  };
  const out: TickerLine[] = [];
  const tagLine = (tag: Tag): TickerLine => ({
    key: `tag-${tag.kind}-${tag.player_id}-${tag.period}-${tag.t}`,
    minute: tag.minute,
    addedMinute: tag.added_minute,
    correctedAt: null,
    ruledOutAt: null,
    ...describeTag(tag, r),
  });
  let next = 0;
  for (const event of events) {
    while (next < tags.length && (event.period > tags[next].period || (event.period === tags[next].period && event.t > tags[next].t))) {
      out.push(tagLine(tags[next++]));
    }
    out.push({
      key: `${event.seq}`,
      minute: event.minute,
      addedMinute: event.added_minute,
      correctedAt: correctedAt(event),
      ruledOutAt: ruledOutAt(event),
      ...describe(event, r),
    });
  }
  for (const tag of tags.slice(next)) out.push(tagLine(tag));
  return out;
}

/** A tag from the tracking: a sprint above the threshold, or a player passing a distance. */
export function describeTag(tag: Tag, r: Roster): EventLine {
  const who = `${name(r, tag.player_id)} (${r.clubName(tag.team_id)})`;
  if (tag.kind === "sprint") {
    return { text: `${who} sprints at ${tag.value.toFixed(1)}${NBSP}km/h${tag.record ? ", the fastest of the match so far" : ""}`, tone: "sprint" };
  }
  return { text: `${who} has covered ${tag.value}${NBSP}km`, tone: "distance" };
}

/**
 * How a correction that moves an event's credit had it and has it now: "credited to X", or "given as
 * an own goal by X", with the names `name` gives. Null for a correction that doesn't move the credit.
 * Shared with the described feed (lib/live/described.ts), so the two say the same.
 */
export function credits(event: FeedEvent, name: (id: unknown) => string): { before: string; after: string } | null {
  const changes = (event.changes ?? {}) as Record<string, { before: unknown; after: unknown } | undefined>;
  const player = changes.player_id;
  if (!player) return null;
  const corrected = (event.corrected_event ?? {}) as { own_goal?: unknown };
  const credit = (side: "before" | "after") => {
    const own = (changes.own_goal ? changes.own_goal[side] : corrected.own_goal) === true;
    return own ? `given as an own goal by ${name(player[side])}` : `credited to ${name(player[side])}`;
  };
  return { before: credit("before"), after: credit("after") };
}

function correction(event: FeedEvent, r: Roster): string {
  const changes = (event.changes ?? {}) as Record<string, unknown>;
  const corrected = (event.corrected_event ?? {}) as { minute?: number; added_minute?: number | null };
  const what =
    typeof corrected.minute === "number" ? `the ${minuteLabel(corrected.minute, corrected.added_minute ?? null)} ${String(event.amends)}` : `the ${String(event.amends)}`;
  const credit = credits(event, (id) => name(r, id));
  if (credit) return `Correction: ${what} is now ${credit.after}; it had been ${credit.before}`;
  return `Correction to ${what}: ${Object.keys(changes).join(", ")}`;
}
