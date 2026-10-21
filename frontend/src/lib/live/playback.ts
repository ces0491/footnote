// Delivery held to each viewer's playback (docs/audience.md, P4: never ahead of the viewer's screen).
//
// A fan's stream runs `delay` seconds behind live, so their playback is live minus the delay, in
// replay seconds (lib/live/timeline.ts). Every event push says when the provider published it
// (`replay`), and every insight names the feed message behind its current state (`shown_seq`): the
// page shows the match folded up to the last event playback has reached, and an insight's state
// once playback reaches the message behind it, or for a segment or stat the stoppage after that.
// Nothing the run sent later is shown. The producer works live, with no delay.
//
// A replay starts at its jump point, so a delayed stream starts there too: until playback reaches
// the start, the page waits, as a stream would.

import type { EventMessage, Insight, RunDescriptor, StateView } from "./contract";
import type { Language } from "./language";
import { foldEvent, type RunViewState } from "./run-reducer";
import { liveReplaySecond } from "./timeline";

/** The stream delays a fan can choose, in seconds of match time: a replay at 2x plays them in half
 * the time, as it plays the match. The pitch view needs a lead to fetch the tracking before playback
 * reaches it, so none is shorter than the first (hooks/use-tracking.ts fetches faster near live). */
export const DELAYS = [3, 10, 20, 40, 60] as const;

/** The least time a graphic stays on screen, in wall seconds, so it stays readable at 2x and 4x. */
export const MIN_ON_SCREEN_SECONDS = 4;

export interface Playback {
  live: number; // the replay second live play is at; once the run has ended, where it ended
  at: number; // the viewer's playback, in replay seconds
  waiting: number; // replay seconds until the stream reaches the replay's start; 0 once it has
}

/**
 * Where live play and the viewer's playback are. `liveEnd` is the replay second a run that has ended
 * stopped at (its last event's): live stays there, while a delayed stream plays on to it, as a
 * stream would after the broadcast ends.
 */
export function playbackOf(run: RunDescriptor, serverNow: number, delay: number, liveEnd = Infinity): Playback {
  const clock = liveReplaySecond(run, serverNow);
  const behind = clock - delay;
  return {
    live: Math.min(clock, liveEnd),
    at: Math.max(run.start_replay, behind),
    waiting: Math.max(0, run.start_replay - behind),
  };
}

/** How far a stream runs behind live, in words: in match seconds, and in real time when the replay
 * runs faster than the match. */
export function delayText(delay: number, speed: number): string {
  if (speed === 1) return `${delay} seconds behind live`;
  const real = delay / speed;
  return `${delay} seconds of match time behind live (${Number.isInteger(real) ? real : real.toFixed(1)} s at ${speed}×)`;
}

/** How long a stream still has to wait, in wall seconds rounded up, in words: "1 second", "12 seconds". */
export function waitText(seconds: number): string {
  const whole = Math.ceil(seconds);
  return `${whole} ${whole === 1 ? "second" : "seconds"}`;
}

/** How many of the events playback at `at` has reached: they are in replay order. */
export function reached(events: EventMessage[], at: number): number {
  let lo = 0;
  let hi = events.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (events[mid].replay <= at) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/** The match after the first `count` events: the base with them folded in; `live` is all of them. */
export function viewAfter(base: StateView | null, events: EventMessage[], live: StateView | null, count: number): StateView | null {
  if (!base) return null;
  if (count >= events.length) return live;
  let view = base;
  for (const message of events.slice(0, count)) view = foldEvent(view, message);
  return view;
}

/**
 * The replay second from which an insight's state may show: when the provider published the feed
 * message behind it, or the next stoppage after that for one held for a stoppage. Null while the
 * page doesn't have that message yet, so the state can't have reached anyone's playback.
 */
export function shownFrom(insight: Insight, state: RunViewState, run: RunDescriptor): number | null {
  const base = state.base;
  if (!base) return null;
  if (insight.shown_seq <= base.seq) return run.start_replay; // before the replay's start
  const first = insight.shown_seq - base.seq - 1; // the events have no gap from the base on
  const events = state.events;
  if (first >= events.length) return null;
  if (insight.hold !== "stoppage") return events[first].replay;
  for (let i = first; i < events.length; i++) if (events[i].stoppage) return events[i].replay;
  return null;
}

export interface Shown {
  insight: Insight; // the state current at the playback
  from: number; // the replay second it showed from
  lang?: Language; // the language its card's wording is in, once localized (lib/live/language.ts)
  earlier?: Insight[]; // the states before it that had reached the playback too, in the order they came
}

/** Each insight as it stood at playback `at`: the latest state that had reached it, with the earlier
 * states that had too. */
export function insightsAt(state: RunViewState, run: RunDescriptor, at: number): Shown[] {
  const out: Shown[] = [];
  for (const states of Object.values(state.history)) {
    const arrived: Shown[] = [];
    for (const insight of states) {
      const from = shownFrom(insight, state, run);
      if (from !== null && from <= at) arrived.push({ insight, from });
    }
    const current = arrived.pop();
    if (current) out.push({ ...current, earlier: arrived.map((s) => s.insight) });
  }
  return out.sort((a, b) => b.from - a.from || b.insight.rank - a.insight.rank);
}

/** What a fan may see: live moments the producer approved, or that were approved automatically. */
export function airing(shown: Shown[]): Shown[] {
  return shown.filter(({ insight }) => insight.live && insight.status === "approved");
}

const SCREEN_PLACES = ["lower_third", "full_card"] as const;

/**
 * The replay second from which a graphic may go on screen for a viewer `delay` seconds behind live.
 * That is when it showed, unless the producer approved a lower third after the viewer's playback had
 * passed it: an approval given after the moment shows the item at once to a viewer already past it
 * (docs/overlay.md), so it goes on from where their playback was at the approval. A full card keeps
 * its time, since starting one later would cover live play (P5).
 */
export function airsFrom(shown: Shown, run: RunDescriptor, delay: number): number {
  const { insight } = shown;
  if (insight.placement !== "lower_third" || insight.status !== "approved" || insight.status_by !== "producer") return shown.from;
  const approvedAt = Date.parse(insight.status_at ?? "");
  if (Number.isNaN(approvedAt)) return shown.from;
  return Math.max(shown.from, liveReplaySecond(run, approvedAt) - delay);
}

/**
 * The graphics on screen at `at` for a viewer `delay` seconds behind live, at most one in each place.
 * In each place they air in turn, as an operator would run them: each from when it may (airsFrom),
 * or when the one before it leaves, whichever is later, for its duration and at least
 * MIN_ON_SCREEN_SECONDS of wall time at the replay's speed. One that would wait more than twice its
 * own time on screen is stale by then and dropped, and a flagged one never airs: VAR or a correction
 * undid it, and the panel says so. Side-panel cards stay in the panel.
 */
export function onScreenAt(shown: Shown[], at: number, run: RunDescriptor, delay: number): Shown[] {
  const out: Shown[] = [];
  for (const place of SCREEN_PLACES) {
    const queue = shown
      .filter((s) => s.insight.placement === place && s.insight.duration !== null && !s.insight.flag)
      .map((s) => ({ s, from: airsFrom(s, run, delay) }))
      .sort((a, b) => a.from - b.from || b.s.insight.rank - a.s.insight.rank);
    let free = -Infinity;
    for (const { s, from } of queue) {
      const length = Math.max(s.insight.duration ?? 0, MIN_ON_SCREEN_SECONDS * run.speed);
      const start = Math.max(from, free);
      if (start - from > 2 * length) continue;
      if (start > at) break;
      free = start + length;
      if (at < free) {
        out.push(s);
        break;
      }
    }
  }
  return out;
}
