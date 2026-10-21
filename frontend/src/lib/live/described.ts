// The described feed (docs/experience.md, "Described feed"; docs/audience.md, P8): a running text
// account of where the ball is, the passes and the build-up, for a screen reader to read out. Each
// line is a template over one event's own fields, so it says only what the event records: a described
// event that didn't happen misleads someone who can't check it by looking.
//
// Three levels of detail. Key moments: goals, shots, VAR, cards, substitutions, the clock, the
// provider's corrections and the graphics that air. Standard adds the build-up: changes of
// possession in open play, passes and runs that take the ball forward, crosses, through balls, fouls,
// offsides and set pieces other than throw-ins. Full adds every pass and run, throw-ins, tackles,
// interceptions, clearances and blocks.

import type { EventMessage, FeedEvent, MatchMeta, Score, StateView } from "./contract";
import { credits, type Roster } from "./describe";
import type { Language } from "./language";
import type { Shown } from "./playback";
import { clockLabel } from "./timeline";

export const DETAILS = { key: "Key moments", standard: "Standard", full: "Full" } as const;
export type Detail = keyof typeof DETAILS;

/** Words the feed says in one language: English, as the page is, or the language of a graphic's
 * wording, so a screen reader can say each in its own voice. */
export interface Part {
  text: string;
  lang: Language;
}

export interface DescribedLine {
  key: string;
  replay: number; // the replay second it belongs to: when its event was published, or its card showed
  clock: string; // the match clock, as a broadcast shows it
  parts: Part[]; // in English, but for a graphic's wording in Spanish or French
  level: Detail;
}

function english(text: string): Part[] {
  return [{ text, lang: "en" }];
}

/** Parts in a row in the same language, as one part. */
function joined(parts: Part[]): Part[] {
  const out: Part[] = [];
  for (const part of parts) {
    const before = out.at(-1);
    if (before?.lang === part.lang) out[out.length - 1] = { text: `${before.text} ${part.text}`, lang: part.lang };
    else out.push(part);
  }
  return out;
}

const LEVEL_RANK: Record<Detail, number> = { key: 0, standard: 1, full: 2 };

/** Whether a line belongs at the detail the listener chose. */
export function atDetail(line: DescribedLine, detail: Detail): boolean {
  return LEVEL_RANK[line.level] <= LEVEL_RANK[detail];
}

// The pitch, in metres (src/footnote/generator/pitch.py).
const LENGTH = 105;
const WIDTH = 68;
const BOX_DEPTH = 16.5;
const BOX_HALF_WIDTH = 20.16;
const CIRCLE = 9.15;
const WING = WIDTH / 3; // the outer thirds of the width are the wings

/** A position as the team in possession sees it: `u` towards the opposition goal, `v` towards its left. */
interface Spot {
  u: number;
  v: number;
}

function spotOf(match: MatchMeta, teamId: unknown, period: number, x: unknown, y: unknown): Spot | null {
  const lineup = match.lineups.find((l) => l.club_id === teamId);
  if (!lineup || typeof x !== "number" || typeof y !== "number") return null;
  const direction = period === 1 ? lineup.attacking_direction.first_half : lineup.attacking_direction.second_half;
  return direction === "+x" ? { u: x, v: y } : { u: LENGTH - x, v: WIDTH - y };
}

/** Where a spot is, in a few words a listener can picture. */
export function where(spot: Spot): string {
  const central = Math.abs(spot.v - WIDTH / 2) <= BOX_HALF_WIDTH;
  if (spot.u >= LENGTH - BOX_DEPTH && central) return "in the box";
  if (spot.u <= BOX_DEPTH && central) return "in their own box";
  if (Math.hypot(spot.u - LENGTH / 2, spot.v - WIDTH / 2) <= CIRCLE) return "in the centre circle";
  const side = spot.v > WIDTH - WING ? " on the left" : spot.v < WING ? " on the right" : "";
  const depth = spot.u < 35 ? "deep in their own half" : spot.u < LENGTH / 2 ? "in their own half" : spot.u < 70 ? "in the opposition half" : "in the final third";
  return depth + side;
}

/** The score as a screen reader says it well: "Saltmarsh 0, Kingsferry 1". */
export function spokenScore(match: MatchMeta, score: Score): string {
  return `${match.home.short_name} ${score.home}, ${match.away.short_name} ${score.away}`;
}

function ordinal(n: number): string {
  const tens = n % 100;
  const suffix = tens >= 11 && tens <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  return `${n}${suffix}`;
}

const SHOT: Record<string, string> = { saved: "saved", blocked: "blocked", off_target: "off target", goal: "goal" };
const FOOT: Record<string, string> = { right_foot: "right foot", left_foot: "left foot", head: "header" };
const RESTART: Record<string, string> = { corner: "Corner", goal_kick: "Goal kick", throw_in: "Throw-in" };
const SET_PIECE: Record<string, string> = { corner: "the corner", free_kick: "the free kick", goal_kick: "the goal kick", throw_in: "the throw-in" };
const WON: Record<string, string> = {
  interception: "intercept",
  tackle: "win the ball with a tackle",
  recovery: "pick up the loose ball",
  duel: "win the ball in a duel",
  claim: "claim the ball",
  save: "keep the ball after the save",
};

interface Said {
  text: string;
  level: Detail;
}

class Teller {
  constructor(
    private readonly match: MatchMeta,
    private readonly r: Roster,
  ) {}

  private name(id: unknown): string {
    const full = this.r.player(id)?.name;
    return full ? full.split(" ").at(-1)! : "a player";
  }

  private club(id: unknown): string {
    return this.r.clubName(id) || "a side";
  }

  private other(id: unknown): string {
    return id === this.match.home.id ? this.match.away.short_name : this.match.home.short_name;
  }

  private at(e: FeedEvent, team: unknown, x: unknown, y: unknown): string | null {
    const spot = spotOf(this.match, team, e.period, x, y);
    return spot ? where(spot) : null;
  }

  private pass(e: FeedEvent): Said | null {
    const passer = this.name(e.player_id);
    const start = spotOf(this.match, e.team_id, e.period, e.x, e.y);
    const end = spotOf(this.match, e.team_id, e.period, e.end_x, e.end_y);
    const to = e.recipient_id ? this.name(e.recipient_id) : null;
    const landing = end ? where(end) : null;
    const outcome = String(e.outcome);
    const result =
      outcome === "complete"
        ? to
          ? ` to ${to}${landing ? `, ${landing}` : ""}`
          : ""
        : outcome === "offside"
          ? `${to ? ` to ${to}, who is` : ", the receiver"} offside`
          : outcome === "out"
            ? ", and it goes out of play"
            : `${to ? ` for ${to}` : ""}, but it doesn't arrive`;
    const type = String(e.pass_type);
    if (type in SET_PIECE) {
      // Throw-ins come every minute or so: only at full detail.
      return { text: `${passer} takes ${SET_PIECE[type]}${result}.`, level: type === "throw_in" ? "full" : "standard" };
    }
    if (type === "kick_off") return { text: `${passer} kicks off.`, level: "full" };
    const forward = start && end ? end.u - start.u : 0;
    const sideways = start && end ? Math.abs(end.v - start.v) : 0;
    const length = typeof e.length === "number" ? e.length : 0;
    const from = start ? `, ${where(start)},` : "";
    if (e.cross) {
      const side = start ? (start.v > WIDTH / 2 ? "the left" : "the right") : "wide";
      return { text: `${passer} crosses from ${side}${result}.`, level: "standard" };
    }
    if (e.through_ball) return { text: `${passer}${from} plays a through ball${result}.`, level: "standard" };
    const kind = length >= 30 ? "long pass" : length < 12 ? "short pass" : "pass";
    // Which way it goes, from its angle: forward or back when it gains or loses more ground than it
    // moves sideways, and across otherwise. Without both ends there is no way to tell.
    const direction = !start || !end ? "" : forward > sideways ? " forward" : -forward > sideways ? " back" : " across";
    // The build-up a listener needs: the ball going forward into the opposition half, or into the box.
    const progressive = forward >= 15 && end !== null && end.u >= LENGTH / 2;
    const intoBox = landing === "in the box";
    return {
      text: `${passer}${from} plays a ${kind}${direction}${result}.`,
      level: progressive || intoBox ? "standard" : "full",
    };
  }

  private carry(e: FeedEvent): Said {
    const start = spotOf(this.match, e.team_id, e.period, e.x, e.y);
    const end = spotOf(this.match, e.team_id, e.period, e.end_x, e.end_y);
    const forward = start && end ? end.u - start.u : 0;
    const into = end ? where(end) : null;
    return {
      text: `${this.name(e.player_id)} runs with the ball${into ? `, ${into}` : ""}.`,
      level: forward >= 15 && end !== null && end.u >= 70 ? "standard" : "full",
    };
  }

  /** What one event says, or null for one the feed doesn't describe. */
  tell(message: EventMessage): Said | null {
    const e = message.event;
    const who = this.name(e.player_id);
    const club = this.club(e.team_id);
    switch (e.type) {
      case "pass":
        return this.pass(e);
      case "carry":
        return this.carry(e);
      case "shot": {
        const foot = FOOT[String(e.body_part)];
        const distance = typeof e.distance === "number" ? ` from ${Math.round(e.distance)} metres` : "";
        const keeper = e.outcome === "saved" && e.goalkeeper_id ? ` by ${this.name(e.goalkeeper_id)}` : "";
        const how = foot === "header" ? "heads at goal" : `shoots${foot ? ` with the ${foot}` : ""}`;
        return { text: `${who} ${how}${distance}: ${SHOT[String(e.outcome)] ?? String(e.outcome)}${keeper}.`, level: "key" };
      }
      case "goal":
        return {
          text: e.own_goal
            ? `Goal for ${club}: an own goal by ${who}. ${spokenScore(this.match, message.score)}.`
            : `Goal for ${club}, scored by ${who}. ${spokenScore(this.match, message.score)}.`,
          level: "key",
        };
      case "var_check": {
        if (e.status === "started") {
          return {
            text:
              e.check === "goal"
                ? `VAR is checking the goal for ${String(e.incident)}.`
                : `VAR is checking for a penalty: ${String(e.incident)} by ${this.name(e.subject_id)}.`,
            level: "key",
          };
        }
        const decision = String(e.decision).replaceAll("_", " ");
        const overturned = e.overturned ? " The decision on the field is overturned." : "";
        return { text: `VAR decision: ${decision}.${overturned} ${spokenScore(this.match, message.score)}.`, level: "key" };
      }
      case "card": {
        if (e.card === "yellow") return { text: `Yellow card for ${who}, ${club}.`, level: "key" };
        const why = e.card === "second_yellow" ? "a second yellow card" : "a straight red card";
        return { text: `${who}, ${club}, is sent off: ${why}.`, level: "key" };
      }
      case "foul":
        if (e.penalty) return { text: `Penalty to ${this.other(e.team_id)}: ${who} fouls ${this.name(e.fouled_id)}.`, level: "key" };
        return { text: `Foul by ${who} on ${this.name(e.fouled_id)}${e.advantage ? "; play goes on" : ""}.`, level: "standard" };
      case "offside":
        return { text: `${who} is caught offside.`, level: "standard" };
      case "ball_out": {
        const restart = String(e.restart);
        const to = e.last_touch_team_id ? ` to ${this.other(e.last_touch_team_id)}` : "";
        return { text: `${RESTART[restart] ?? "The ball goes out"}${to}.`, level: restart === "throw_in" ? "full" : "standard" };
      }
      case "possession_change": {
        if (e.cause === "restart") return null; // the restart's own line tells it
        const place = this.at(e, e.team_id, e.x, e.y);
        return { text: `${club} ${WON[String(e.cause)] ?? "win the ball"}${place ? `, ${place}` : ""}.`, level: "standard" };
      }
      case "substitution":
        return { text: `${club} substitution: ${this.name(e.player_on_id)} comes on for ${this.name(e.player_off_id)}.`, level: "key" };
      case "injury":
        return { text: `${who} is down injured.`, level: "standard" };
      case "added_time":
        return { text: `${String(e.minutes)} minute${e.minutes === 1 ? "" : "s"} of added time.`, level: "key" };
      case "period_start":
        return { text: e.period === 1 ? "Kick-off." : "The second half is under way.", level: "key" };
      case "period_end":
        return { text: `${e.period === 1 ? "Half-time" : "Full time"}. ${spokenScore(this.match, message.score)}.`, level: "key" };
      case "match_end":
        return null; // the final whistle's period_end says it
      case "amendment":
        return { text: this.correction(e), level: "key" };
      case "goalkeeper":
        return e.action === "save" ? null : { text: `${who} claims the ball.`, level: "full" }; // a save is told with its shot
      case "tackle":
        return { text: `${who} ${e.outcome === "won" ? "wins" : "goes in for"} a tackle.`, level: "full" };
      case "interception":
        return { text: `${who} intercepts.`, level: "full" };
      case "clearance":
        return { text: `${who} clears${e.body_part === "head" ? " with a header" : ""}.`, level: "full" };
      case "block":
        return { text: `${who} blocks.`, level: "full" };
      default:
        return null; // pressure, duels, recoveries: the changes of possession tell what matters
    }
  }

  private correction(e: FeedEvent): string {
    const corrected = (e.corrected_event ?? {}) as { minute?: number };
    const when = typeof corrected.minute === "number" ? `the ${ordinal(corrected.minute)}-minute ${String(e.amends)}` : `the ${String(e.amends)}`;
    // The new credit first and the old one in a sentence of its own, so neither reads as the other.
    const credit = credits(e, (id) => this.name(id));
    if (credit) return `Correction from the data provider: ${when} is now ${credit.after}. It had been ${credit.before}.`;
    return `Correction from the data provider to ${when}.`;
  }
}

/** How often the feed speaks, in wall seconds between announcements (RNIB's focus groups found some
 * audio description "too frantic and overwhelming", docs/audience.md). */
export const PACES = {
  relaxed: { label: "Relaxed", seconds: 8 },
  normal: { label: "Normal", seconds: 4 },
  quick: { label: "Quick", seconds: 1.5 },
} as const;
export type Pace = keyof typeof PACES;

/**
 * What to say next, from the lines not yet said, in order and each once. Up to three lines waiting
 * are said in full: a pass and the shot it sets up often reach playback within one announcement.
 * When more have backed up in play (a fast replay), the listener catches up instead of hearing stale
 * build-up: every key moment among them, with the line just before it when that one is its build-up,
 * and the latest line. After a pause the announcement says so, and gives every key moment that
 * waited and the latest line.
 */
export function nextSaying(backlog: DescribedLine[], resumed: boolean): Part[] | null {
  if (backlog.length === 0) return null;
  const last = backlog.length - 1;
  const said =
    backlog.length <= 3
      ? backlog
      : backlog.filter((l, i) => i === last || l.level === "key" || (!resumed && backlog[i + 1].level === "key"));
  return joined([...(resumed ? english("While paused:") : []), ...said.flatMap((l) => l.parts)]);
}

/** The line a replay's feed opens with: the score and the minute it starts at. */
export function openingLine(match: MatchMeta, base: StateView, replay: number): DescribedLine {
  const clock = base.clock;
  const text =
    base.phase === "pre_match" || !clock
      ? `${match.home.name} against ${match.away.name}. Kick-off is coming up.`
      : `${spokenScore(match, base.score)}, in the ${ordinal(clock.minute)} minute.`;
  return { key: "opening", replay, clock: clock ? clockLabel({ period: clock.period === 1 ? 1 : 2, t: clock.t }) : "", parts: english(text), level: "key" };
}

/** The opening line and a line for each event the viewer's playback has reached (lib/live/playback.ts). */
export function eventLines(match: MatchMeta, r: Roster, base: StateView, startReplay: number, events: EventMessage[]): DescribedLine[] {
  const teller = new Teller(match, r);
  const lines: DescribedLine[] = [openingLine(match, base, startReplay)];
  for (const message of events) {
    const said = teller.tell(message);
    if (!said) continue;
    const e = message.event;
    const clock = clockLabel({ period: e.period === 1 ? 1 : 2, t: e.t });
    lines.push({ key: `e${message.seq}`, replay: message.replay, clock, parts: english(said.text), level: said.level });
  }
  return lines;
}

/** A line for each graphic airing for the viewer, read out when it shows, as RNIB asks of text on
 * screen, in the language its wording is in. One VAR or a correction undid isn't read: the decision
 * or the notice is. A line is keyed on the graphic, so a graphic is read once: a later wording of
 * it, the agent's after the template's or a translation, isn't read again, and one not yet read is
 * read as it now stands. A producer's edit is read again: it may put right what was said. */
export function cardLines(cards: Shown[]): DescribedLine[] {
  return cards
    .filter((s) => !s.insight.flag)
    .map((s) => ({
      key: `card-${s.insight.insight_id}${s.insight.source === "producer" ? `-v${s.insight.version}` : ""}`,
      replay: s.from,
      clock: "",
      parts: joined([...english("On screen:"), { text: s.insight.card.plain, lang: s.lang ?? "en" }]),
      level: "key" as const,
    }));
}

/** Event lines and card lines in the order they happened; a graphic after the event that brought it. */
export function merged(events: DescribedLine[], cards: DescribedLine[]): DescribedLine[] {
  return [...events, ...cards].sort((a, b) => a.replay - b.replay);
}
