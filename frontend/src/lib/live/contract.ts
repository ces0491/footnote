// The viewer side of the contract in src/footnote/live/contract.py: what the processor pushes to a
// run's Web PubSub group, and what the web app's API returns.

import { z } from "zod";

export const SPEEDS = [1, 2, 4] as const;

export const startRunRequest = z.object({
  start_minute: z.number().int().min(1).max(90),
  speed: z.union(SPEEDS.map((s) => z.literal(s))),
});
export type StartRunRequest = z.infer<typeof startRunRequest>;

export const runIdPattern = /^[0-9a-f]{16}$/;

export function groupName(runId: string): string {
  return `run-${runId}`;
}

export type Phase = "pre_match" | "first_half" | "half_time" | "second_half" | "full_time";
export type RunEndReason = "finished" | "stopped" | "expired" | "evicted" | "failed";
export type RunStatus = "running" | RunEndReason;

export interface RunDescriptor {
  run_id: string;
  match_id: string;
  speed: number;
  start_minute: number;
  start_replay: number;
  created_at: number;
  started_at: number; // epoch ms at which the run's start point is live
  backfill_seq: number;
  last_seq: number;
  timeline: { first_half_end: number; half_time: number };
}

export interface Clock {
  period: number;
  t: number;
  clock: number;
  minute: number;
  added_minute: number | null;
}

export interface TeamStats {
  shots: number;
  on_target: number;
  passes: number;
  passes_completed: number;
  corners: number;
  fouls: number;
  offsides: number;
  yellow_cards: number;
  red_cards: number;
  pass_accuracy: number | null;
  possession: number | null;
  // From the models and the tracking (src/footnote/live/analysis.py).
  pass_length?: number | null; // metres, throw-ins excluded
  pass_difficulty?: number | null; // average, 0-1
  distance_km?: number | null;
  top_shot_kmh?: number | null;
}

export type MatchStateKind = "control" | "pressure" | "transition" | "chaos" | "balanced";

/** The state model's estimate, `second` seconds into `period`: a few seconds behind the feed. */
export interface MatchState {
  period: number;
  second: number;
  state: MatchStateKind;
  team_id: string | null;
  confidence: number;
  on_top: Score; // chance each side holds a state of its own (control, pressure or a break)
}

/** A spell of one state, from the first to the last second it was the estimate. */
export interface StateSpell {
  period: number;
  state: MatchStateKind;
  team_id: string | null;
  start: number;
  end: number;
}

export interface PlayerLine {
  player_id: string;
  passes: number;
  completed: number;
  difficulty: number | null;
  hardest: number | null;
  hardest_minute: number | null;
  distance_km?: number;
  top_speed_kmh?: number;
}

export interface Tag {
  kind: "sprint" | "distance";
  player_id: string;
  team_id: string;
  value: number;
  unit: "km/h" | "km";
  period: number;
  t: number;
  minute: number;
  added_minute: number | null;
  record: boolean; // a sprint faster than any before it in the match
}

export interface Score {
  home: number;
  away: number;
}

/** A feed message as pushed: provider boilerplate and freeze frames dropped. */
export interface FeedEvent {
  seq: number;
  event_id: string;
  version: number;
  type: string;
  period: number;
  t: number;
  clock: number;
  minute: number;
  added_minute: number | null;
  team_id?: string;
  player_id?: string;
  [field: string]: unknown;
}

export interface LiveFields {
  seq: number;
  phase: Phase;
  clock: Clock | null;
  score: Score;
  teams: Record<string, TeamStats>;
  match_state?: MatchState | null;
}

export interface StateView extends LiveFields {
  key_events: FeedEvent[];
  state_timeline?: StateSpell[];
  players?: Record<string, PlayerLine>;
  tags?: Tag[];
}

export interface Timing {
  published_at?: number;
  enqueued_at?: number | null;
  processed_at?: number;
}

export interface SnapshotMessage extends StateView {
  type: "snapshot";
  run_id: string;
  run: RunDescriptor;
  timing: Timing;
}

export interface EventMessage extends LiveFields {
  type: "event";
  run_id: string;
  event: FeedEvent;
  key: boolean;
  timing: Timing;
  difficulty?: number | null; // a pass's difficulty, 0-1
  player?: PlayerLine; // the line of the player on the event, after it
  tags?: Tag[]; // tags that fell due with this event
}

export interface RunEndMessage {
  type: "run_end";
  run_id: string;
  reason: RunEndReason;
  timing: Timing;
}

export type PushMessage = SnapshotMessage | EventMessage | RunEndMessage;

export interface Player {
  player_id: string;
  name: string;
  shirt: number;
  position: string;
}

export interface Club {
  id: string;
  code: string;
  name: string;
  short_name: string;
  colours: [string, string];
  formation: string;
}

export interface MatchMeta {
  match_id: string;
  competition: string;
  season: string;
  venue: string;
  kickoff: string;
  referee: { id: string; name: string };
  home: Club;
  away: Club;
  lineups: { club_id: string; formation: string; starters: Player[]; bench: Player[] }[];
}

/** GET /api/runs/[runId] */
export interface RunSnapshot {
  run: RunDescriptor;
  status: RunStatus;
  view: StateView | null;
  match: MatchMeta;
  server_time: number;
}
