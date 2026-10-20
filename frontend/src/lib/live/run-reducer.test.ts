import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import type {
  EventMessage,
  Insight,
  InsightMessage,
  MatchState,
  PlayerLine,
  PushMessage,
  RunEndReason,
  StateSpell,
  StateView,
  Tag,
} from "./contract";
import { initialRunViewState, type RunAction, runReducer, type RunViewState, timelineAfter } from "./run-reducer";
import { insightFixture } from "./test-fixtures";

// Shared with the processor's tests, so both sides fold estimates into the same timeline.
const FIXTURE = JSON.parse(readFileSync(new URL("../../../../tests/fixtures/state_timeline.json", import.meta.url), "utf-8")) as {
  states: (MatchState | null)[];
  timeline: StateSpell[];
};

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

  it("folds each push's match state into the timeline, the same way the processor does", () => {
    expect(FIXTURE.states.reduce(timelineAfter, [] as StateSpell[])).toEqual(FIXTURE.timeline);
    const pushes = FIXTURE.states.map((state, i) => push({ ...event(11 + i), match_state: state }));
    const state = run([snapshot({ ...view(10), state_timeline: [] }), ...pushes]);
    expect(state.view?.state_timeline).toEqual(FIXTURE.timeline);
    expect(state.view?.match_state).toEqual(FIXTURE.states.at(-1));
  });

  it("replaces the line of the player on each event and adds tags", () => {
    const line = (passes: number): PlayerLine => ({
      player_id: "sal-10",
      passes,
      completed: passes,
      difficulty: 0.3,
      hardest: 0.6,
      hardest_minute: 12,
    });
    const tag: Tag = {
      kind: "sprint",
      player_id: "kin-07",
      team_id: "kin",
      value: 33.9,
      unit: "km/h",
      period: 1,
      t: 700.2,
      minute: 12,
      added_minute: null,
      record: true,
    };
    const start = { ...view(10), players: { "sal-10": line(4) }, tags: [] };
    const state = run([snapshot(start), push({ ...event(11), player: line(5) }), push({ ...event(12), tags: [tag] })]);
    expect(state.view?.players?.["sal-10"].passes).toBe(5);
    expect(state.view?.tags).toEqual([tag]);
  });
});

const insightPush = (rev: number, insight: Insight): InsightMessage => ({ type: "insight", run_id: "0123456789abcdef", rev, insight });
const snapshotWith = (rev: number, insights: Insight[]): RunAction => ({
  kind: "snapshot",
  view: view(10),
  ended: null,
  insights,
  insightRev: rev,
});

describe("runReducer, insights", () => {
  it("applies insight pushes in revision order on top of the snapshot", () => {
    const template = insightFixture("goal-e0391");
    const agent = insightFixture("goal-e0391", { version: 2, source: "agent", agent_state: "done" });
    const state = run([snapshotWith(4, []), push(insightPush(5, template)), push(insightPush(6, agent))]);
    expect(state.insightRev).toBe(6);
    expect(state.insights["goal-e0391"].source).toBe("agent");
  });

  it("drops a revision it already has and asks for a snapshot after a gap", () => {
    const first = run([snapshotWith(5, [insightFixture("a")]), push(insightPush(5, insightFixture("a", { rank: 0.1 })))]);
    expect(first.insights.a.rank).toBe(0.95); // rev 5 was already in the snapshot
    const gap = runReducer(first, push(insightPush(7, insightFixture("b"))));
    expect(gap.snapshotRequests).toBe(first.snapshotRequests + 1);
    expect(gap.insights.b).toBeUndefined();
    const filled = runReducer(gap, snapshotWith(7, [insightFixture("a"), insightFixture("b")]));
    expect(filled.insightRev).toBe(7);
    expect(Object.keys(filled.insights).sort()).toEqual(["a", "b"]);
  });

  it("keeps the insights it has when a snapshot carries older ones", () => {
    const state = run([snapshotWith(3, []), push(insightPush(4, insightFixture("a"))), snapshotWith(3, [])]);
    expect(state.insightRev).toBe(4);
    expect(state.insights.a).toBeDefined();
  });
});
