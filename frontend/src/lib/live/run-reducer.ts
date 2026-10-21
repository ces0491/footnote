// Folding what a run sends into what its page knows. The match comes from pushes: the snapshot at
// the end of the replay's backfill (the base), then every event in seq order, each carrying the
// state after it. The processor stores each push with its feed row, so a page fetches what it lacks
// (GET /api/runs/[runId]/pushes) and holds new pushes meanwhile, and its events never have a gap.
// From the base and the events the page can show the match as of any moment since the replay's
// start: live for the producer, and as of their own playback for a fan whose stream runs behind
// (lib/live/playback.ts).
//
// Insights follow their own counter. Each change to one bumps the run's insight revision, and its
// push carries the revision it made; the processor, the agents and the producer's desk all push
// them. A revision already held is dropped, and a gap (a missed push, or two pushes crossing on the
// way) asks for a fresh snapshot, which carries every insight and the revision they are as of. Each
// insight's states are kept in the order they came, so a page can show the one that was current at
// its playback; the pushes are stored too (GET /api/runs/[runId]/insights), so a page that loads
// late, or misses some, still has the earlier states.

import type {
  EventMessage,
  Insight,
  InsightMessage,
  MatchState,
  PushMessage,
  RunEndReason,
  SnapshotMessage,
  StateSpell,
  StateView,
} from "./contract";

/**
 * The state timeline once a pushed estimate is folded in: the last spell extends, or a new one
 * starts. The processor builds the snapshot's timeline by the same rule
 * (src/footnote/live/analysis.py, timeline_after), so the two agree.
 */
export function timelineAfter(timeline: StateSpell[], state: MatchState | null | undefined): StateSpell[] {
  if (!state) return timeline;
  const last = timeline.at(-1);
  if (last && last.period === state.period && last.state === state.state && last.team_id === state.team_id) {
    return last.end === state.second ? timeline : [...timeline.slice(0, -1), { ...last, end: state.second }];
  }
  return [...timeline, { period: state.period, state: state.state, team_id: state.team_id, start: state.second, end: state.second }];
}

/** The match before kick-off, the base of a replay that starts there. */
export const KICK_OFF_VIEW: StateView = {
  seq: 0,
  phase: "pre_match",
  clock: null,
  score: { home: 0, away: 0 },
  teams: {},
  match_state: null,
  key_events: [],
  state_timeline: [],
  players: {},
  tags: [],
};

/** The match after one more event: its push carries the live fields; the histories grow. */
export function foldEvent(view: StateView, message: EventMessage): StateView {
  const { seq, phase, clock, score, teams, match_state } = message;
  return {
    seq,
    phase,
    clock,
    score,
    teams,
    match_state,
    key_events: message.key ? [...view.key_events, message.event] : view.key_events,
    state_timeline: timelineAfter(view.state_timeline ?? [], match_state),
    players: message.player ? { ...view.players, [message.player.player_id]: message.player } : view.players,
    tags: message.tags?.length ? [...(view.tags ?? []), ...message.tags] : view.tags,
  };
}

function viewOf(message: SnapshotMessage): StateView {
  const { seq, phase, clock, score, teams, match_state, key_events, state_timeline, players, tags } = message;
  return { seq, phase, clock, score, teams, match_state, key_events, state_timeline, players, tags };
}

export interface RunViewState {
  /** The match at the replay's start; null until the page has it. */
  base: StateView | null;
  /** Every event after the base, in seq order, without a gap. */
  events: EventMessage[];
  /** The match live: the base with every event folded in. */
  view: StateView | null;
  ended: RunEndReason | null;
  /** Pushes waiting for a resync that is on its way; null when none is. */
  held: PushMessage[] | null;
  /** Bumped each time the page should fetch the snapshot and the pushes it lacks. */
  resyncs: number;
  insights: Record<string, Insight>;
  /** Each insight's states in the order they came, the current one last. */
  history: Record<string, Insight[]>;
  /** The insight revision `insights` is as of; null until the first snapshot. */
  insightRev: number | null;
}

// The page fetches what it needs before it connects, so pushes start out held.
export const initialRunViewState: RunViewState = {
  base: null,
  events: [],
  view: null,
  ended: null,
  held: [],
  resyncs: 0,
  insights: {},
  history: {},
  insightRev: null,
};

export type RunAction =
  | { kind: "push"; message: PushMessage }
  // The connection has (re)opened, and pushes sent while it was closed are lost.
  | { kind: "resync" }
  // What a resync fetched: the stored pushes after the page's last event, the run's status, from the
  // snapshot its insights, and the stored insight pushes after the page's last revision, which keep
  // each card's earlier states for a page that wasn't there when they changed. `backfillSeq` is the
  // descriptor's: 0 for a replay from kick-off.
  | {
      kind: "resynced";
      pushes: (SnapshotMessage | EventMessage)[];
      ended: RunEndReason | null;
      backfillSeq: number;
      insights?: Insight[];
      insightRev?: number;
      insightPushes?: InsightMessage[];
    };

function requestResync(state: RunViewState, held: PushMessage[]): RunViewState {
  return { ...state, held, resyncs: state.resyncs + 1 };
}

function same(a: Insight, b: Insight): boolean {
  return a.updated_at === b.updated_at && a.version === b.version && a.status === b.status;
}

function remember(history: Record<string, Insight[]>, insight: Insight): Record<string, Insight[]> {
  const states = history[insight.insight_id] ?? [];
  const last = states.at(-1);
  return last && same(last, insight) ? history : { ...history, [insight.insight_id]: [...states, insight] };
}

function applyBase(state: RunViewState, message: SnapshotMessage): RunViewState {
  // A run's base never changes; a later snapshot push is one the page already has.
  if (state.base) return state;
  const base = viewOf(message);
  return { ...state, base, view: base, events: [] };
}

function applyEvent(state: RunViewState, message: EventMessage): RunViewState {
  const view = state.view;
  if (view && message.seq <= view.seq) return state; // redelivered, or already fetched
  // No base yet, or a push was missed: hold this one until a resync covers the gap.
  if (!view || message.seq !== view.seq + 1) return requestResync(state, [message]);
  return { ...state, events: [...state.events, message], view: foldEvent(view, message) };
}

function applyInsight(state: RunViewState, message: InsightMessage): RunViewState {
  const rev = state.insightRev;
  if (rev !== null && message.rev <= rev) return state; // already applied, or in the snapshot
  if (rev === null || message.rev !== rev + 1) return requestResync(state, [message]);
  return {
    ...state,
    insights: { ...state.insights, [message.insight.insight_id]: message.insight },
    history: remember(state.history, message.insight),
    insightRev: message.rev,
  };
}

function apply(state: RunViewState, message: PushMessage): RunViewState {
  switch (message.type) {
    case "snapshot":
      return applyBase(state, message);
    case "event":
      return applyEvent(state, message);
    case "insight":
      return applyInsight(state, message);
    case "run_end":
      return { ...state, ended: message.reason };
  }
}

/** An insight change with the next revision: it needs nothing a resync on its way could bring. */
function nextInsight(state: RunViewState, message: PushMessage): boolean {
  return message.type === "insight" && state.insightRev !== null && message.rev === state.insightRev + 1;
}

export function runReducer(state: RunViewState, action: RunAction): RunViewState {
  switch (action.kind) {
    case "push":
      if (state.held && !nextInsight(state, action.message)) return { ...state, held: [...state.held, action.message] };
      return apply(state, action.message);
    case "resync":
      return requestResync(state, state.held ?? []);
    case "resynced": {
      let next: RunViewState = { ...state, held: null, ended: action.ended ?? state.ended };
      if (!next.base && action.backfillSeq === 0) next = { ...next, base: KICK_OFF_VIEW, view: KICK_OFF_VIEW, events: [] };
      // Every state each card went through, in the order they happened, before the snapshot's
      // current ones: a delayed screen shows the one its playback has reached.
      let past = next.history;
      for (const message of action.insightPushes ?? []) past = remember(past, message.insight);
      next = { ...next, history: past };
      const fresher =
        action.insights !== undefined &&
        action.insightRev !== undefined &&
        (state.insightRev === null || action.insightRev >= state.insightRev);
      if (fresher) {
        let history = next.history;
        for (const insight of action.insights!) history = remember(history, insight);
        next = {
          ...next,
          insights: Object.fromEntries(action.insights!.map((i) => [i.insight_id, i])),
          history,
          insightRev: action.insightRev!,
        };
      }
      // Fetched or held, pushes go through the same checks; one that reveals a gap holds the rest
      // for another resync.
      for (const message of [...action.pushes, ...(state.held ?? [])]) next = runReducer(next, { kind: "push", message });
      return next;
    }
  }
}
