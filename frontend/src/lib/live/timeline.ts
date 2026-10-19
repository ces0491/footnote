// Replay time on the client, mirroring src/footnote/live/timeline.py: replay seconds run from
// kick-off with the half-time break shortened to `half_time` seconds.

import type { RunDescriptor } from "./contract";

const PERIOD_SECONDS = 45 * 60;

export interface Moment {
  period: 1 | 2;
  t: number;
}

/** The period and seconds into it a replay second shows, or null during the break. */
export function moment(replay: number, timeline: RunDescriptor["timeline"]): Moment | null {
  if (replay <= timeline.first_half_end) return { period: 1, t: Math.max(0, replay) };
  if (replay < timeline.first_half_end + timeline.half_time) return null;
  return { period: 2, t: replay - timeline.first_half_end - timeline.half_time };
}

/** Where live play is at `serverNow` (epoch ms on the server's clock). */
export function liveReplaySecond(run: RunDescriptor, serverNow: number): number {
  const elapsed = Math.max(0, serverNow - run.started_at) / 1000;
  return run.start_replay + elapsed * run.speed;
}

/** The match clock as a broadcast shows it: 23:41, or 45+2:10 in added time. */
export function clockLabel(m: Moment): string {
  const base = m.period === 1 ? 0 : PERIOD_SECONDS;
  const capped = Math.min(m.t, PERIOD_SECONDS);
  const shown = base + capped;
  const main = `${Math.floor(shown / 60)}:${String(Math.floor(shown % 60)).padStart(2, "0")}`;
  if (m.t <= PERIOD_SECONDS) return main;
  const extra = m.t - PERIOD_SECONDS;
  return `${(base + PERIOD_SECONDS) / 60}+${Math.floor(extra / 60)}:${String(Math.floor(extra % 60)).padStart(2, "0")}`;
}

/** The broadcast minute of an event: 23' or 45+2'. */
export function minuteLabel(minute: number, addedMinute: number | null): string {
  return addedMinute ? `${minute}+${addedMinute}'` : `${minute}'`;
}
