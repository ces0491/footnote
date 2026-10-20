import { describe, expect, it } from "vitest";

import type { EventMessage, PushMessage, RunEndReason, StateView } from "./contract";
import { initialRunViewState, type RunAction, runReducer, type RunViewState } from "./run-reducer";

const SCORE = { home: 0, away: 0 };

function view(seq: number, keySeqs: number[] = []): StateView {
  return {
    seq,
    phase: "first_half",
    clock: null,
    score: SCORE,
    teams: {},
    key_events: keySeqs.map((s) => feedEvent(s)),
  };
}

function feedEvent(seq: number) {
  return { seq, event_id: `e${seq}`, version: 1, type: "shot", period: 1, t: seq, clock: seq, minute: 1, added_minute: null };
}

function event(seq: number, key = false): EventMessage {
  return {
    type: "event",
    run_id: "0123456789abcdef",
    event: feedEvent(seq),
    key,
    seq,
    phase: "first_half",
    clock: null,
    score: SCORE,
    teams: {},
    timing: {},
  };
}

const push = (message: PushMessage): RunAction => ({ kind: "push", message });
const snapshot = (v: StateView | null, ended: RunEndReason | null = null): RunAction => ({ kind: "snapshot", view: v, ended });
const runEnd = (reason: RunEndReason): PushMessage => ({ type: "run_end", run_id: "0123456789abcdef", reason, timing: {} });

function run(actions: RunAction[], from: RunViewState = initialRunViewState): RunViewState {
  return actions.reduce(runReducer, from);
}

const keySeqs = (state: RunViewState) => state.view?.key_events.map((e) => e.seq);

describe("runReducer", () => {
  it("holds pushes until the first snapshot, then applies those it doesn't cover", () => {
    const state = run([push(event(11)), push(event(12, true)), snapshot(view(11))]);
    expect(state.view?.seq).toBe(12);
    expect(keySeqs(state)).toEqual([12]);
    expect(state.held).toBeNull();
    expect(state.snapshotRequests).toBe(0);
  });

  it("applies pushes in sequence and keeps the key ones", () => {
    const state = run([snapshot(view(10)), push(event(11)), push(event(12, true)), push(event(13))]);
    expect(state.view?.seq).toBe(13);
    expect(keySeqs(state)).toEqual([12]);
  });

  it("ignores a push it has already applied", () => {
    const once = run([snapshot(view(10)), push(event(11, true))]);
    expect(runReducer(once, push(event(11, true)))).toBe(once);
  });

  it("holds pushes after a gap and asks for a snapshot", () => {
    const state = run([snapshot(view(10)), push(event(12)), push(event(13))]);
    expect(state.view?.seq).toBe(10);
    expect(state.held?.map((m) => (m.type === "event" ? m.seq : null))).toEqual([12, 13]);
    expect(state.snapshotRequests).toBe(1);
  });

  it("keeps the missed key event when newer pushes arrive while the snapshot is fetched", () => {
    // 11 is lost; 12 reveals the gap; 13 arrives before the snapshot, which only reaches 12.
    const state = run([snapshot(view(10)), push(event(12)), push(event(13, true)), snapshot(view(12, [11]))]);
    expect(state.view?.seq).toBe(13);
    expect(keySeqs(state)).toEqual([11, 13]);
    expect(state.held).toBeNull();
    expect(state.snapshotRequests).toBe(1);
  });

  it("asks again when the held pushes still leave a gap", () => {
    const state = run([snapshot(view(10)), push(event(12)), push(event(14)), snapshot(view(12))]);
    expect(state.view?.seq).toBe(12);
    expect(state.held?.map((m) => (m.type === "event" ? m.seq : null))).toEqual([14]);
    expect(state.snapshotRequests).toBe(2);
  });

  it("asks for a snapshot on resync and keeps what it already holds", () => {
    const gapped = run([snapshot(view(10)), push(event(12))]);
    const state = runReducer(gapped, { kind: "resync" });
    expect(state.snapshotRequests).toBe(2);
    expect(state.held).toHaveLength(1);
    const fresh = runReducer(run([snapshot(view(10))]), { kind: "resync" });
    expect(fresh.held).toEqual([]);
    expect(fresh.snapshotRequests).toBe(1);
  });

  it("asks for a snapshot when an event arrives before there is any state", () => {
    const state = run([snapshot(null), push(event(5))]);
    expect(state.view).toBeNull();
    expect(state.snapshotRequests).toBe(1);
    expect(run([snapshot(view(5))], state).view?.seq).toBe(5);
  });

  it("takes a pushed snapshot only when it is at least as new", () => {
    const current = run([snapshot(view(10)), push(event(11))]);
    const older: PushMessage = { type: "snapshot", run_id: "0123456789abcdef", run: {} as never, timing: {}, ...view(9) };
    expect(runReducer(current, push(older)).view?.seq).toBe(11);
    const newer: PushMessage = { ...older, ...view(20, [15]) };
    expect(keySeqs(runReducer(current, push(newer)))).toEqual([15]);
  });

  it("marks the run ended from a push or from a snapshot, and a stale snapshot doesn't undo it", () => {
    expect(run([snapshot(view(10)), push(runEnd("finished"))]).ended).toBe("finished");
    expect(run([snapshot(view(10), "stopped")]).ended).toBe("stopped");
    const ended = run([snapshot(view(10)), push(runEnd("finished"))]);
    expect(runReducer(ended, snapshot(view(10))).ended).toBe("finished");
  });
});
