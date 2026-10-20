// The viewer side of the contract in src/footnote/live/contract.py: what the processor pushes to a
// run's Web PubSub group, and what the web app's API returns.

import { z } from "zod";

export const SPEEDS = [1, 2, 4] as const;

/** How a run's graphics are approved: automatically as they're found, or by the producer. */
export const PRODUCER_MODES = ["auto", "manual"] as const;
export type ProducerMode = (typeof PRODUCER_MODES)[number];

/** The anonymous ID a browser goes by (lib/live/viewer.ts): a random UUID. */
export const viewerIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

export const startRunRequest = z.object({
  start_minute: z.number().int().min(1).max(90),
  speed: z.union(SPEEDS.map((s) => z.literal(s))),
  viewer: z.string().regex(viewerIdPattern).optional(), // a new start replaces this viewer's last
  producer: z.enum(PRODUCER_MODES).optional(),
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
  replay: number; // the replay second at which the provider published it
  stoppage: boolean; // play is stopped after it
  timing?: Timing; // on live pushes only; a stored push has none
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

// --- Insights: the overlay contract (docs/overlay.md, src/footnote/live/overlay.py) -------------

export type InsightKind = "moment" | "rule_call" | "segment" | "stat" | "player_tag" | "recap" | "correction";
export type AgentState = "off" | "pending" | "drafting" | "done" | "fallback";
export type InsightStatus = "drafted" | "approved" | "withdrawn" | "killed";
export type WordingSource = "template" | "agent" | "producer";

/** When something happened, in match time: each client holds an insight against its own playback. */
export interface MatchTime {
  period: number;
  t: number;
  minute?: number;
  added_minute?: number | null;
}

/** An insight's wording with its figures filled in by code. */
export interface InsightCard {
  headline: string;
  casual: string;
  analyst: string;
  plain: string; // for screen readers
  evidence: string[]; // event IDs: those cited, then those behind the facts used
  facts: string[]; // the fact keys the wording used
}

export interface Provenance {
  source: WordingSource;
  template?: string;
  agent_run_id?: string;
  model?: string;
  prompt?: string;
  attempts?: number;
  tools?: string[];
  latency_ms?: number;
  checks?: string;
  cached?: boolean;
  edited_from?: number; // the version a producer edited
}

export interface InsightFlag {
  reason: string;
  event_id: string;
  version: number;
  seq: number;
}

/** One item of the overlay contract: an insight as it now stands. */
export interface Insight {
  match_id: string;
  insight_id: string;
  seq: number; // the feed message its facts are as of
  kind: InsightKind;
  topic: string; // also the graphics template that shows it
  at: MatchTime; // when it happened
  until: MatchTime; // leaves the shortlist after this
  shown_seq: number; // the feed message behind its current state: shown once playback reaches it
  shown_at: MatchTime; // that message's match time
  ts: string; // that message's timestamp from the provider
  rank: number;
  reason: string;
  evidence: string[];
  placement: "lower_third" | "side_panel" | "full_card";
  hold: "stoppage" | null; // wait for the next stoppage after shown_at
  duration: number | null; // seconds of match time on screen; null for a side-panel card
  motion: "still" | "animated";
  corrects: string | null;
  live: boolean; // false for moments the run's backfill passed
  flag: InsightFlag | null; // VAR or a correction undid what it cites
  status: InsightStatus; // only an approved item airs
  status_by: "auto" | "producer" | "correction" | null;
  status_at: string | null;
  agent_state: AgentState;
  agent_note: string | null; // why the template stands, when it does
  version: number;
  source: WordingSource;
  card: InsightCard;
  fields: Record<string, string>; // each fact's text, for graphics systems filling a template
  provenance: Provenance;
  created_at: string;
  updated_at: string;
}

/** An insight that changed, with the run's insight revision the change made. */
export interface InsightMessage {
  type: "insight";
  run_id: string;
  rev: number;
  insight: Insight;
  timing?: Timing;
}

export type PushMessage = SnapshotMessage | EventMessage | RunEndMessage | InsightMessage;

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
  lineups: {
    club_id: string;
    formation: string;
    attacking_direction: { first_half: "+x" | "-x"; second_half: "+x" | "-x" };
    starters: Player[];
    bench: Player[];
  }[];
}

/** How the tracking chunks for the pitch view are laid out (src/footnote/live/pitch.py). */
export interface TrackingLayout {
  frame_rate: number;
  frames_per_chunk: number;
  values_per_frame: number;
  frames: Record<string, number>; // frames in each period, by period
  slot_players: string[][]; // the player in each of the 22 slots, per line-up
}

/** GET /api/runs/[runId] */
export interface RunSnapshot {
  run: RunDescriptor;
  status: RunStatus;
  producer: ProducerMode;
  view: StateView | null;
  match: MatchMeta;
  tracking: TrackingLayout | null;
  insights: Insight[];
  insight_rev: number; // the revision the insights are as of
  server_time: number;
}

/** GET /api/runs/[runId]/pushes?after=<seq>: what viewers were sent after `seq`, as stored with
 * each feed row: the snapshot at the end of the backfill, then every event. */
export interface PushesResponse {
  pushes: (SnapshotMessage | EventMessage)[];
  more: boolean; // a page limit cut it short: ask again after the last
}

/** GET /api/runs/[runId]/events?ids=... : the events an insight cites, as they stand. */
export interface EvidenceResponse {
  events: FeedEvent[];
}

// --- The producer's desk (src/footnote/agents/desk.py) ------------------------------------------

export interface Sentence {
  text: string;
  events: string[];
}

/** A card's wording before code fills its placeholders in: `{fact.key}` where each figure goes. */
export interface Draft {
  headline: string;
  casual: Sentence[];
  analyst: Sentence[];
}

const sentence = z.object({ text: z.string().max(400), events: z.array(z.string().regex(/^e\d{4,6}$/)).max(24) });
export const draftSchema = z.object({
  headline: z.string().max(200),
  casual: z.array(sentence).max(4),
  analyst: z.array(sentence).max(5),
});

export const DESK_ACTIONS = ["approve", "kill", "withdraw", "redraft", "edit"] as const;
export type DeskAction = (typeof DESK_ACTIONS)[number];

export const deskActionRequest = z.discriminatedUnion("action", [
  z.object({ action: z.enum(["approve", "kill", "withdraw", "redraft"]), viewer: z.string().regex(viewerIdPattern) }),
  z.object({ action: z.literal("edit"), viewer: z.string().regex(viewerIdPattern), draft: draftSchema }),
]);
export type DeskActionRequest = z.infer<typeof deskActionRequest>;

export const producerModeRequest = z.object({
  viewer: z.string().regex(viewerIdPattern),
  mode: z.enum(PRODUCER_MODES),
});

/** What the desk says when it won't act: why, and for an edit, what failed the checks. */
export interface DeskRefusal {
  error: string;
  problems: string[];
}

export interface AgentRunSummary {
  agent_run_id: string;
  started_at: string;
  finished_at: string | null;
  outcome: "accepted" | "rejected" | "timeout" | "error" | "superseded" | null;
  attempts: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  reasoning_tokens: number | null;
  latency_ms: number | null;
  problems: string[] | null;
  tool_calls: { name: string; arguments: Record<string, unknown> }[] | null;
  error: string | null;
}

/** GET /api/runs/[runId]/insights/[insightId]: what the console needs to edit a card and to show
 * the agents' work on it. */
export interface InsightDetail {
  draft: Draft; // the wording to start an edit from
  draft_from: "current" | "template";
  facts: { key: string; display: string; about: string }[];
  agent_runs: AgentRunSummary[];
}
