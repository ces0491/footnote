// One line per key event for the match ticker, filled from the event's own fields. Templates only:
// a line says what the event records and nothing more.

import type { FeedEvent, MatchMeta, Player } from "./contract";

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

export type EventTone = "goal" | "var" | "card" | "correction" | "period" | "plain";

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
    case "shot":
      return { text: `${name(r, event.player_id)} (${club}) shoots: ${SHOT_OUTCOME[String(event.outcome)] ?? event.outcome}`, tone: "plain" };
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
    default:
      return { text: event.type.replaceAll("_", " "), tone: "plain" };
  }
}

function correction(event: FeedEvent, r: Roster): string {
  const changes = (event.changes ?? {}) as Record<string, { before: unknown; after: unknown }>;
  if (changes.player_id) {
    const before = name(r, changes.player_id.before);
    const after = name(r, changes.player_id.after);
    const wasOwnGoal = changes.own_goal?.before === true;
    return `Correction: ${String(event.amends)} now credited to ${after}, not ${before}${wasOwnGoal ? " (own goal)" : ""}`;
  }
  return `Correction to the ${String(event.amends)}: ${Object.keys(changes).join(", ")}`;
}
