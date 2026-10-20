// Fixtures shared by the tests beside this file. Nothing in the app imports it.

import type { EventMessage, FeedEvent, Insight, RunDescriptor, SnapshotMessage } from "./contract";

const RUN_ID = "0123456789abcdef";

export function runFixture(overrides: Partial<RunDescriptor> = {}): RunDescriptor {
  return {
    run_id: RUN_ID,
    match_id: "fl-2627-showcase-sal-kin",
    speed: 1,
    start_minute: 23,
    start_replay: 1290,
    created_at: 1_800_000_000_000,
    started_at: 1_800_000_002_000,
    backfill_seq: 10,
    last_seq: 1819,
    timeline: { first_half_end: 3082.59, half_time: 30 },
    ...overrides,
  };
}

export function feedEventFixture(seq: number, overrides: Partial<FeedEvent> = {}): FeedEvent {
  return { seq, event_id: `e${String(seq).padStart(4, "0")}`, version: 1, type: "pass", period: 1, t: 1290 + seq, clock: 1290 + seq, minute: 22, added_minute: null, ...overrides };
}

/** The stored snapshot at the end of a replay's backfill. */
export function baseSnapshot(seq: number): SnapshotMessage {
  return {
    type: "snapshot",
    run_id: RUN_ID,
    run: runFixture({ backfill_seq: seq }),
    timing: {},
    seq,
    phase: "first_half",
    clock: null,
    score: { home: 0, away: 0 },
    teams: {},
    key_events: [],
  };
}

/** An event push, published `seq` replay seconds after the base's start by default. */
export function eventPush(seq: number, overrides: Partial<EventMessage> = {}): EventMessage {
  return {
    type: "event",
    run_id: RUN_ID,
    event: feedEventFixture(seq),
    key: false,
    replay: 1290 + seq,
    stoppage: false,
    seq,
    phase: "first_half",
    clock: null,
    score: { home: 0, away: 0 },
    teams: {},
    ...overrides,
  };
}

export function insightFixture(id: string, overrides: Partial<Insight> = {}): Insight {
  return {
    match_id: "fl-2627-showcase-sal-kin",
    insight_id: id,
    seq: 392,
    kind: "moment",
    topic: "goal",
    at: { period: 1, t: 1357.25, minute: 23, added_minute: null },
    until: { period: 1, t: 1657.25 },
    shown_seq: 392,
    shown_at: { period: 1, t: 1357.25, minute: 23, added_minute: null },
    ts: "2027-03-07T13:22:37.250Z",
    rank: 0.95,
    reason: "Goal: against the run of play",
    evidence: ["e0391"],
    placement: "lower_third",
    hold: null,
    duration: 12,
    motion: "animated",
    corrects: null,
    live: true,
    flag: null,
    status: "approved",
    status_by: "auto",
    status_at: "2026-10-20T12:00:00Z",
    agent_state: "pending",
    agent_note: null,
    version: 1,
    source: "template",
    card: { headline: "Femi Adeyani scores", casual: "", analyst: "", plain: "", evidence: ["e0391"], facts: [] },
    fields: { "moment.scorer": "Femi Adeyani" },
    provenance: { source: "template", template: "goal" },
    created_at: "2026-10-20T12:00:00Z",
    updated_at: "2026-10-20T12:00:00Z",
    ...overrides,
  };
}
