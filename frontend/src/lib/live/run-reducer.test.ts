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
  SnapshotMessage,
  StateSpell,
  Tag,
} from "./contract";
import { initialRunViewState, KICK_OFF_VIEW, type RunAction, runReducer, type RunViewState, timelineAfter } from "./run-reducer";
import { baseSnapshot, eventPush, insightFixture } from "./test-fixtures";

// Shared with the processor's tests, so both sides fold estimates into the same timeline.
const FIXTURE = JSON.parse(readFileSync(new URL("../../../../tests/fixtures/state_timeline.json", import.meta.url), "utf-8")) as {
  states: (MatchState | null)[];
  timeline: StateSpell[];
};

const push = (message: PushMessage): RunAction => ({ kind: "push", message });
const resynced = (
  pushes: (SnapshotMessage | EventMessage)[],
  { ended = null, backfillSeq = 10, insights, insightRev }: { ended?: RunEndReason | null; backfillSeq?: number; insights?: Insight[]; insightRev?: number } = {},
): RunAction => ({ kind: "resynced", pushes, ended, backfillSeq, insights, insightRev });
const runEnd = (reason: RunEndReason): PushMessage => ({ type: "run_end", run_id: "0123456789abcdef", reason, timing: {} });

function run(actions: RunAction[], from: RunViewState = initialRunViewState): RunViewState {
  return actions.reduce(runReducer, from);
}

const keySeqs = (state: RunViewState) => state.view?.key_events.map((e) => e.seq);
const seqs = (state: RunViewState) => state.events.map((e) => e.seq);

describe("runReducer, the match", () => {
  it("starts from the stored snapshot and folds every event after it", () => {
    const state = run([resynced([baseSnapshot(10), eventPush(11), eventPush(12, { key: true })])]);
    expect(state.base?.seq).toBe(10);
    expect(seqs(state)).toEqual([11, 12]);
    expect(state.view?.seq).toBe(12);
    expect(keySeqs(state)).toEqual([12]);
  });

  it("holds pushes until the first resync, then applies those it doesn't cover", () => {
    const state = run([push(eventPush(11)), push(eventPush(12, { key: true })), resynced([baseSnapshot(10), eventPush(11)])]);
    expect(seqs(state)).toEqual([11, 12]);
    expect(keySeqs(state)).toEqual([12]);
    expect(state.held).toBeNull();
    expect(state.resyncs).toBe(0);
  });

  it("ignores a push it already has", () => {
    const once = run([resynced([baseSnapshot(10), eventPush(11, { key: true })])]);
    expect(runReducer(once, push(eventPush(11, { key: true })))).toBe(once);
  });

  it("holds pushes after a gap and asks for what it missed", () => {
    const state = run([resynced([baseSnapshot(10)]), push(eventPush(12)), push(eventPush(13))]);
    expect(state.view?.seq).toBe(10);
    expect(state.held?.map((m) => (m.type === "event" ? m.seq : null))).toEqual([12, 13]);
    expect(state.resyncs).toBe(1);
    const filled = runReducer(state, resynced([eventPush(11, { key: true }), eventPush(12)]));
    expect(seqs(filled)).toEqual([11, 12, 13]);
    expect(keySeqs(filled)).toEqual([11]);
    expect(filled.held).toBeNull();
  });

  it("asks again when what it fetched still leaves a gap", () => {
    const state = run([resynced([baseSnapshot(10)]), push(eventPush(12)), push(eventPush(14)), resynced([eventPush(11)])]);
    expect(seqs(state)).toEqual([11, 12]);
    expect(state.held?.map((m) => (m.type === "event" ? m.seq : null))).toEqual([14]);
    expect(state.resyncs).toBe(2);
  });

  it("asks for a resync when the connection opens, keeping what it holds", () => {
    const gapped = run([resynced([baseSnapshot(10)]), push(eventPush(12))]);
    const state = runReducer(gapped, { kind: "resync" });
    expect(state.resyncs).toBe(2);
    expect(state.held).toHaveLength(1);
    const fresh = runReducer(run([resynced([baseSnapshot(10)])]), { kind: "resync" });
    expect(fresh.held).toEqual([]);
    expect(fresh.resyncs).toBe(1);
  });

  it("waits for the base when events come before it: a replay still backfilling", () => {
    const state = run([resynced([]), push(eventPush(11))]);
    expect(state.view).toBeNull();
    expect(state.resyncs).toBe(1);
    expect(run([resynced([baseSnapshot(10)])], state).view?.seq).toBe(11);
  });

  it("takes the pushed snapshot as the base, and only the first", () => {
    const state = run([resynced([]), push(baseSnapshot(10)), push(eventPush(11)), push(baseSnapshot(12))]);
    expect(state.base?.seq).toBe(10);
    expect(state.view?.seq).toBe(11);
  });

  it("starts a replay from kick-off before any event", () => {
    const state = run([resynced([eventPush(1), eventPush(2)], { backfillSeq: 0 })]);
    expect(state.base).toBe(KICK_OFF_VIEW);
    expect(seqs(state)).toEqual([1, 2]);
  });

  it("marks the run ended from a push or from a resync, and a stale resync doesn't undo it", () => {
    expect(run([resynced([baseSnapshot(10)]), push(runEnd("finished"))]).ended).toBe("finished");
    expect(run([resynced([baseSnapshot(10)], { ended: "stopped" })]).ended).toBe("stopped");
    const ended = run([resynced([baseSnapshot(10)]), push(runEnd("finished"))]);
    expect(runReducer(ended, resynced([])).ended).toBe("finished");
  });

  it("folds each push's match state into the timeline, the same way the processor does", () => {
    expect(FIXTURE.states.reduce(timelineAfter, [] as StateSpell[])).toEqual(FIXTURE.timeline);
    const pushes = FIXTURE.states.map((state, i) => eventPush(11 + i, { match_state: state }));
    const state = run([resynced([{ ...baseSnapshot(10), state_timeline: [] }, ...pushes])]);
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
    const start = { ...baseSnapshot(10), players: { "sal-10": line(4) }, tags: [] };
    const state = run([resynced([start, eventPush(11, { player: line(5) }), eventPush(12, { tags: [tag] })])]);
    expect(state.view?.players?.["sal-10"].passes).toBe(5);
    expect(state.view?.tags).toEqual([tag]);
  });
});

const insightPush = (rev: number, insight: Insight): InsightMessage => ({ type: "insight", run_id: "0123456789abcdef", rev, insight });
const withInsights = (rev: number, insights: Insight[]) => resynced([], { insights, insightRev: rev });

describe("runReducer, insights", () => {
  it("applies insight pushes in revision order on top of the snapshot, keeping each state", () => {
    const template = insightFixture("goal-e0391");
    const agent = insightFixture("goal-e0391", { version: 2, source: "agent", agent_state: "done", updated_at: "2026-10-20T12:00:09Z" });
    const state = run([withInsights(4, []), push(insightPush(5, template)), push(insightPush(6, agent))]);
    expect(state.insightRev).toBe(6);
    expect(state.insights["goal-e0391"].source).toBe("agent");
    expect(state.history["goal-e0391"].map((i) => i.version)).toEqual([1, 2]);
  });

  it("drops a revision it already has and asks for a snapshot after a gap", () => {
    const first = run([withInsights(5, [insightFixture("a")]), push(insightPush(5, insightFixture("a", { rank: 0.1 })))]);
    expect(first.insights.a.rank).toBe(0.95); // rev 5 was already in the snapshot
    const gap = runReducer(first, push(insightPush(7, insightFixture("b"))));
    expect(gap.resyncs).toBe(first.resyncs + 1);
    expect(gap.insights.b).toBeUndefined();
    const filled = runReducer(gap, withInsights(7, [insightFixture("a"), insightFixture("b")]));
    expect(filled.insightRev).toBe(7);
    expect(Object.keys(filled.insights).sort()).toEqual(["a", "b"]);
    expect(filled.history.a).toHaveLength(1); // the snapshot's copy is the state it had
  });

  it("applies the next revision at once, even while a resync is on its way", () => {
    const waiting = runReducer(run([withInsights(4, [])]), { kind: "resync" });
    expect(waiting.held).toEqual([]);
    const applied = runReducer(waiting, push(insightPush(5, insightFixture("a"))));
    expect(applied.insights.a).toBeDefined();
    expect(applied.held).toEqual([]);
    const later = runReducer(applied, push(insightPush(7, insightFixture("b"))));
    expect(later.held).toHaveLength(1); // a gap still waits for the resync
  });

  it("keeps the insights it has when a snapshot carries older ones", () => {
    const state = run([withInsights(3, []), push(insightPush(4, insightFixture("a"))), withInsights(3, [])]);
    expect(state.insightRev).toBe(4);
    expect(state.insights.a).toBeDefined();
  });
});
