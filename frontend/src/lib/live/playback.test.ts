import { describe, expect, it } from "vitest";

import { airing, delayText, insightsAt, onScreenAt, playbackOf, reached, shownFrom, viewAfter } from "./playback";
import { initialRunViewState, runReducer, type RunViewState } from "./run-reducer";
import { baseSnapshot, eventPush, insightFixture, runFixture } from "./test-fixtures";

const run = runFixture(); // starts at replay second 1290, live from started_at

/** A page that has the base at seq 10 and events 11-20, each published at 1290 + seq. */
function page(extra: Partial<RunViewState> = {}): RunViewState {
  const events = Array.from({ length: 10 }, (_, i) =>
    eventPush(11 + i, { key: i === 4, stoppage: i === 6, score: { home: 0, away: i >= 4 ? 1 : 0 } }),
  );
  const loaded = runReducer(initialRunViewState, {
    kind: "resynced",
    pushes: [baseSnapshot(10), ...events],
    ended: null,
    backfillSeq: 10,
    insights: [],
    insightRev: 0,
  });
  return { ...loaded, ...extra };
}

describe("playback", () => {
  it("runs the delay behind live, and waits at the replay's start until the stream gets there", () => {
    const at = (wall: number, delay: number) => playbackOf(run, run.started_at + wall * 1000, delay);
    expect(at(100, 3)).toEqual({ live: 1390, at: 1387, waiting: 0 });
    expect(at(10, 40)).toEqual({ live: 1300, at: 1290, waiting: 30 });
    const fast = playbackOf({ ...run, speed: 4 }, run.started_at + 100_000, 40);
    expect(fast.live).toBe(1690);
    expect(fast.at).toBe(1650);
  });

  it("holds live where a run ended, while a delayed stream plays on to it", () => {
    // Stopped at replay second 1310: nothing beyond it exists, but a stream 40 s behind still has it to play.
    expect(playbackOf(run, run.started_at + 30_000, 40, 1310)).toEqual({ live: 1310, at: 1290, waiting: 10 });
    expect(playbackOf(run, run.started_at + 100_000, 40, 1310)).toEqual({ live: 1310, at: 1350, waiting: 0 });
  });

  it("says how far behind a stream is in match time, and in real time when the replay runs fast", () => {
    expect(delayText(40, 1)).toBe("40 seconds behind live");
    expect(delayText(40, 2)).toBe("40 seconds of match time behind live (20 s at 2×)");
    expect(delayText(3, 4)).toBe("3 seconds of match time behind live (0.8 s at 4×)");
  });

  it("shows a delayed screen a card as it stood before VAR, for a page that loaded after the decision", () => {
    const goal = insightFixture("goal-e0015", { shown_seq: 15 });
    const ruledOut = {
      ...goal,
      flag: { reason: "Ruled out by VAR", event_id: "e0015", version: 1, seq: 17 },
      shown_seq: 17,
      updated_at: "2026-10-20T12:01:00Z",
    };
    const events = Array.from({ length: 10 }, (_, i) => eventPush(11 + i));
    const state = runReducer(initialRunViewState, {
      kind: "resynced",
      pushes: [baseSnapshot(10), ...events],
      ended: null,
      backfillSeq: 10,
      insights: [ruledOut], // the snapshot has only the card as it now stands
      insightRev: 2,
      insightPushes: [
        { type: "insight", run_id: run.run_id, rev: 1, insight: goal },
        { type: "insight", run_id: run.run_id, rev: 2, insight: ruledOut },
      ],
    });
    // Event 15 was published at replay second 1305, the decision (17) at 1307.
    expect(insightsAt(state, run, 1306).map((s) => s.insight.flag)).toEqual([null]);
    expect(insightsAt(state, run, 1307).map((s) => s.insight.flag?.seq)).toEqual([17]);
  });

  it("folds the match up to the last event playback has reached", () => {
    const state = page();
    expect(reached(state.events, 1290)).toBe(0);
    expect(reached(state.events, 1301)).toBe(1); // seq 11, published at 1301
    expect(reached(state.events, 1305.5)).toBe(5);
    expect(reached(state.events, 9999)).toBe(10);
    const after = (count: number) => viewAfter(state.base, state.events, state.view, count);
    expect(after(0)?.seq).toBe(10);
    const midway = after(4);
    expect(midway?.seq).toBe(14);
    expect(midway?.score).toEqual({ home: 0, away: 0 }); // the goal at seq 15 hasn't reached playback
    expect(after(5)?.score).toEqual({ home: 0, away: 1 });
    expect(after(10)).toBe(state.view);
  });

  it("shows an insight from the message behind it, or for a held one the stoppage after", () => {
    const state = page();
    expect(shownFrom(insightFixture("goal", { shown_seq: 15 }), state, run)).toBe(1305);
    expect(shownFrom(insightFixture("old", { shown_seq: 8 }), state, run)).toBe(1290);
    expect(shownFrom(insightFixture("ahead", { shown_seq: 25 }), state, run)).toBeNull();
    const held = insightFixture("spell", { kind: "segment", hold: "stoppage", shown_seq: 13 });
    expect(shownFrom(held, state, run)).toBe(1307); // seq 17 is the stoppage
    expect(shownFrom({ ...held, shown_seq: 18 }, state, run)).toBeNull(); // no stoppage since
  });

  it("shows the state an insight had at playback, never a later one", () => {
    const goal = insightFixture("goal-e0015", { shown_seq: 15 });
    // VAR rules it out at seq 19: the flagged state may show only once playback reaches 19.
    const ruledOut = insightFixture("goal-e0015", {
      shown_seq: 19,
      flag: { reason: "Ruled out by VAR", event_id: "e0019", version: 1, seq: 19 },
      updated_at: "2026-10-20T12:00:30Z",
    });
    const state = page({ history: { "goal-e0015": [goal, ruledOut] } });
    expect(insightsAt(state, run, 1304)).toEqual([]);
    expect(insightsAt(state, run, 1306)[0].insight.flag).toBeNull();
    expect(insightsAt(state, run, 1310)[0].insight.flag?.reason).toBe("Ruled out by VAR");
  });

  it("airs only live moments that were approved", () => {
    const state = page({
      history: {
        a: [insightFixture("a", { shown_seq: 12 })],
        b: [insightFixture("b", { shown_seq: 12, status: "drafted", status_by: null })],
        c: [insightFixture("c", { shown_seq: 12, status: "withdrawn", status_by: "producer" })],
        d: [insightFixture("d", { shown_seq: 12, live: false })],
      },
    });
    expect(airing(insightsAt(state, run, 1400)).map((s) => s.insight.insight_id)).toEqual(["a"]);
  });

  it("keeps a graphic on screen for its duration, and long enough to read at speed", () => {
    const goal = { insight: insightFixture("goal", { duration: 12 }), from: 1305 };
    const ids = (at: number, speed = 1) => onScreenAt([goal], at, speed).map((s) => s.insight.insight_id);
    expect(ids(1304)).toEqual([]);
    expect(ids(1316)).toEqual(["goal"]);
    expect(ids(1317)).toEqual([]);
    expect(ids(1320, 4)).toEqual(["goal"]); // four wall seconds at 4x are 16 replay seconds
    const panel = { insight: insightFixture("spell", { placement: "side_panel", duration: null }), from: 1305 };
    expect(onScreenAt([panel], 1306, 1)).toEqual([]);
  });

  it("runs graphics that show together in turn, strongest first, and never one VAR or a correction undid", () => {
    const goal = { insight: insightFixture("goal", { rank: 0.85 }), from: 1305 };
    const check = { insight: insightFixture("var", { kind: "rule_call", rank: 0.7 }), from: 1305 };
    const recap = { insight: insightFixture("ht", { kind: "recap", placement: "full_card", duration: 20 }), from: 1306 };
    const ids = (shown: typeof goal[], at: number) => onScreenAt(shown, at, 1).map((s) => s.insight.insight_id);
    expect(ids([check, goal, recap], 1310)).toEqual(["goal", "ht"]);
    expect(ids([check, goal], 1318)).toEqual(["var"]); // after the goal's twelve seconds
    expect(ids([check, goal], 1330)).toEqual([]);
    const ruledOut = { ...goal, insight: { ...goal.insight, flag: { reason: "Ruled out by VAR", event_id: "e1", version: 1, seq: 9 } } };
    expect(ids([ruledOut, check], 1306)).toEqual(["var"]);
    // One that would wait more than twice its own time on screen doesn't air at all.
    const brief = { insight: insightFixture("brief", { rank: 0.1, duration: 4 }), from: 1305 };
    expect(ids([goal, check, brief], 1328)).toEqual(["var"]);
    expect(ids([goal, check, brief], 1330)).toEqual([]);
    expect(ids([goal, brief], 1318)).toEqual([]); // waited twelve seconds, more than twice its four
  });
});
