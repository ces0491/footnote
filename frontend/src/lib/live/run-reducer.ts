// Folding pushes into what the live page shows. Every push carries the state after its event, so
// applying one is a replacement, not arithmetic. A gap in seq means a push was missed: the key-event
// list may be missing an entry, so the page fetches the snapshot again.

import type { EventMessage, PushMessage, RunEndReason, StateView } from "./contract";

export interface RunViewState {
  view: StateView | null;
  ended: RunEndReason | null;
  needsSnapshot: boolean;
}

export const initialRunViewState: RunViewState = { view: null, ended: null, needsSnapshot: false };

export type RunAction = { kind: "push"; message: PushMessage } | { kind: "snapshot"; view: StateView | null; ended: RunEndReason | null };

function applyEvent(state: RunViewState, message: EventMessage): RunViewState {
  const view = state.view;
  if (!view) return { ...state, needsSnapshot: true };
  if (message.seq <= view.seq) return state; // redelivered, or already in the snapshot
  const { seq, phase, clock, score, teams } = message;
  const keyEvents = message.key ? [...view.key_events, message.event] : view.key_events;
  return {
    ...state,
    view: { seq, phase, clock, score, teams, key_events: keyEvents },
    needsSnapshot: state.needsSnapshot || message.seq !== view.seq + 1,
  };
}

export function runReducer(state: RunViewState, action: RunAction): RunViewState {
  if (action.kind === "snapshot") {
    const current = state.view;
    const view = action.view && (!current || action.view.seq >= current.seq) ? action.view : current;
    return { view, ended: action.ended ?? state.ended, needsSnapshot: false };
  }
  const message = action.message;
  switch (message.type) {
    case "snapshot": {
      const { seq, phase, clock, score, teams, key_events } = message;
      return runReducer(state, { kind: "snapshot", view: { seq, phase, clock, score, teams, key_events }, ended: null });
    }
    case "event":
      return applyEvent(state, message);
    case "run_end":
      return { ...state, ended: message.reason };
  }
}
