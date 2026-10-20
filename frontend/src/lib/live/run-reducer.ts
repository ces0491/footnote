// Folding pushes into what the live page shows. Every push carries the state after its event, so
// applying one is a replacement, not arithmetic. A snapshot fetched from the web app replaces it in
// the same way. While a snapshot is on its way, pushes are held and applied on top of it once it
// arrives, so nothing received in the meantime is lost or applied out of order. A gap in seq means a
// push was missed and the histories (key events, the state timeline, player lines, tags) may be
// missing an entry, so the reducer asks for a snapshot.
//
// Insights follow their own counter. Each change to one bumps the run's insight revision, and its
// push carries the revision it made; the processor and the agents service both push them. A
// revision already held is dropped, and a gap (a missed push, or two pushes crossing on the way)
// asks for a snapshot, which carries every insight and the revision they are as of.

import type {
  EventMessage,
  Insight,
  InsightMessage,
  MatchState,
  PushMessage,
  RunEndReason,
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

export interface RunViewState {
  view: StateView | null;
  ended: RunEndReason | null;
  /** Pushes waiting for a snapshot that is on its way; null when none is. */
  held: PushMessage[] | null;
  /** Bumped each time a fresh snapshot is needed. The page fetches one whenever it changes. */
  snapshotRequests: number;
  insights: Record<string, Insight>;
  /** The insight revision `insights` is as of; null until the first snapshot. */
  insightRev: number | null;
}

// The page fetches the first snapshot itself before it connects, so pushes start out held.
export const initialRunViewState: RunViewState = {
  view: null,
  ended: null,
  held: [],
  snapshotRequests: 0,
  insights: {},
  insightRev: null,
};

export type RunAction =
  | { kind: "push"; message: PushMessage }
  | {
      kind: "snapshot";
      view: StateView | null;
      ended: RunEndReason | null;
      insights?: Insight[];
      insightRev?: number;
    }
  // The connection has (re)opened, and pushes sent while it was closed are lost.
  | { kind: "resync" };

function newer(candidate: StateView | null, current: StateView | null): StateView | null {
  return candidate && (!current || candidate.seq >= current.seq) ? candidate : current;
}

function requestSnapshot(state: RunViewState, held: PushMessage[]): RunViewState {
  return { ...state, held, snapshotRequests: state.snapshotRequests + 1 };
}

function applyEvent(state: RunViewState, message: EventMessage): RunViewState {
  const view = state.view;
  if (view && message.seq <= view.seq) return state; // redelivered, or already in the snapshot
  // No state yet, or a push was missed: hold this one until a snapshot covers the gap.
  if (!view || message.seq !== view.seq + 1) return requestSnapshot(state, [message]);
  const { seq, phase, clock, score, teams, match_state } = message;
  const next: StateView = {
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
  return { ...state, view: next };
}

function applyInsight(state: RunViewState, message: InsightMessage): RunViewState {
  const rev = state.insightRev;
  if (rev !== null && message.rev <= rev) return state; // already applied, or in the snapshot
  if (rev === null || message.rev !== rev + 1) return requestSnapshot(state, [message]);
  return {
    ...state,
    insights: { ...state.insights, [message.insight.insight_id]: message.insight },
    insightRev: message.rev,
  };
}

function apply(state: RunViewState, message: PushMessage): RunViewState {
  switch (message.type) {
    case "snapshot": {
      const { seq, phase, clock, score, teams, match_state, key_events, state_timeline, players, tags } = message;
      const view = { seq, phase, clock, score, teams, match_state, key_events, state_timeline, players, tags };
      return { ...state, view: newer(view, state.view) };
    }
    case "event":
      return applyEvent(state, message);
    case "insight":
      return applyInsight(state, message);
    case "run_end":
      return { ...state, ended: message.reason };
  }
}

export function runReducer(state: RunViewState, action: RunAction): RunViewState {
  switch (action.kind) {
    case "push":
      return state.held ? { ...state, held: [...state.held, action.message] } : apply(state, action.message);
    case "resync":
      return requestSnapshot(state, state.held ?? []);
    case "snapshot": {
      const fresher =
        action.insights !== undefined &&
        action.insightRev !== undefined &&
        (state.insightRev === null || action.insightRev >= state.insightRev);
      let next: RunViewState = {
        ...state,
        view: newer(action.view, state.view),
        ended: action.ended ?? state.ended,
        held: null,
        ...(fresher
          ? { insights: Object.fromEntries(action.insights!.map((i) => [i.insight_id, i])), insightRev: action.insightRev! }
          : {}),
      };
      // A held push can itself reveal a gap the snapshot doesn't cover; the rest are then held again.
      for (const message of state.held ?? []) next = runReducer(next, { kind: "push", message });
      return next;
    }
  }
}
