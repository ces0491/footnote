// @vitest-environment jsdom
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  EventMessage,
  InsightMessage,
  MatchMeta,
  PushMessage,
  RunSnapshot,
  RunStatus,
  SnapshotMessage,
} from "@/lib/live/contract";
import { baseSnapshot, eventPush, insightFixture, runFixture } from "@/lib/live/test-fixtures";

import { steady, useLiveRun } from "./use-live-run";

// A stand-in for the Web PubSub client: the tests decide when it connects and what it receives.
const { FakeClient, clients } = vi.hoisted(() => {
  type Handler = (e: unknown) => void;
  const clients: InstanceType<typeof FakeClient>[] = [];
  class FakeClient {
    static refuse = false; // start() fails, as when the service turns a connection away
    started = 0;
    stopped = 0;
    private handlers = new Map<string, Handler[]>();
    constructor(private readonly credential: { getClientAccessUrl: () => Promise<string> }) {
      clients.push(this);
    }
    on(event: string, handler: Handler) {
      this.handlers.set(event, [...(this.handlers.get(event) ?? []), handler]);
    }
    emit(event: string, e: unknown = {}) {
      for (const handler of this.handlers.get(event) ?? []) handler(e);
    }
    receive(message: unknown) {
      this.emit("group-message", { message: { data: message } });
    }
    async start() {
      this.started += 1;
      await this.credential.getClientAccessUrl();
      if (FakeClient.refuse) throw new Error("Failed to start WebSocket: 1006");
    }
    stop() {
      this.stopped += 1;
    }
  }
  return { FakeClient, clients };
});
vi.mock("@azure/web-pubsub-client", () => ({ WebPubSubClient: FakeClient }));

const RUN_ID = "0123456789abcdef";

// Snapshot requests wait until a test answers them, so it controls what arrives first. The stored
// pushes and insight pushes are answered at once, from what the test has put in `stored` and
// `storedInsights`.
let snapshotRequests: ((response: Response) => void)[] = [];
let stored: (SnapshotMessage | EventMessage)[] = [];
let storedInsights: InsightMessage[] = [];
let pushRequests: number[] = [];

function fetchStub(input: RequestInfo | URL): Promise<Response> {
  const url = new URL(String(input), "http://localhost");
  if (url.pathname === "/api/time") return Promise.resolve(Response.json({ now: Date.now() }));
  if (url.pathname.endsWith("/negotiate")) return Promise.resolve(Response.json({ url: "wss://example.test/client" }));
  if (url.pathname.endsWith("/pushes")) {
    const after = Number(url.searchParams.get("after"));
    pushRequests.push(after);
    return Promise.resolve(Response.json({ pushes: stored.filter((p) => p.seq > after), more: false }));
  }
  if (url.pathname.endsWith("/insights")) {
    const after = Number(url.searchParams.get("after"));
    return Promise.resolve(Response.json({ pushes: storedInsights.filter((p) => p.rev > after), more: false }));
  }
  return new Promise((resolve) => snapshotRequests.push(resolve));
}

function snapshot(status: RunStatus = "running"): RunSnapshot {
  return {
    run: runFixture({ run_id: RUN_ID, backfill_seq: 10 }),
    status,
    producer: "auto",
    view: null,
    match: {} as MatchMeta,
    tracking: null,
    insights: [],
    insight_rev: 0,
    server_time: Date.now(),
  };
}

/** The pushes the processor stored for the run up to `seq`, with key events at `keys`. */
function storedUpTo(seq: number, keys: number[] = []): (SnapshotMessage | EventMessage)[] {
  return [baseSnapshot(10), ...Array.from({ length: seq - 10 }, (_, i) => eventPush(11 + i, { key: keys.includes(11 + i) }))];
}

const runEnd = (reason: "finished"): PushMessage => ({ type: "run_end", run_id: RUN_ID, reason, timing: {} });

async function respond(index: number, response: Response, timeout = 3_000) {
  await waitFor(() => expect(snapshotRequests.length).toBeGreaterThan(index), { timeout });
  await act(async () => snapshotRequests[index](response));
}

const unavailable = () => Response.json({ error: "unavailable" }, { status: 503 });

const answer = (index: number, value: RunSnapshot) => respond(index, Response.json(value));

/** Render the hook and bring it to a live, connected state at `seq`. */
async function connectedAt(seq: number) {
  stored = storedUpTo(seq);
  const hook = renderHook(() => useLiveRun(RUN_ID));
  await answer(0, snapshot());
  await waitFor(() => expect(clients[0].started).toBe(1));
  act(() => clients[0].emit("connected"));
  await answer(1, snapshot());
  await waitFor(() => expect(hook.result.current.view?.seq).toBe(seq));
  return hook;
}

const keys = (hook: { result: { current: ReturnType<typeof useLiveRun> } }) =>
  hook.result.current.view?.key_events.map((e) => e.seq);

beforeEach(() => {
  snapshotRequests = [];
  stored = [];
  storedInsights = [];
  pushRequests = [];
  clients.length = 0;
  FakeClient.refuse = false;
  vi.stubGlobal("fetch", vi.fn(fetchStub));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("useLiveRun", () => {
  it("waits while the run is starting, then shows it from its start", async () => {
    stored = storedUpTo(12);
    const hook = renderHook(() => useLiveRun(RUN_ID));
    await respond(0, Response.json({ status: "starting" }, { status: 202 }));
    await answer(1, snapshot());
    await waitFor(() => expect(hook.result.current.view?.seq).toBe(12));
    expect(hook.result.current.state.base?.seq).toBe(10);
    expect(pushRequests[0]).toBe(0);
    expect(hook.result.current.error).toBeNull();
  });

  it("says so when there is no such run", async () => {
    const hook = renderHook(() => useLiveRun(RUN_ID));
    await respond(0, Response.json({ error: "no such run" }, { status: 404 }));
    await waitFor(() => expect(hook.result.current.error).toBe("There's no such replay."));
    expect(clients).toHaveLength(0);
  });

  it("tries the first load again when it fails", async () => {
    stored = storedUpTo(10);
    const hook = renderHook(() => useLiveRun(RUN_ID));
    await respond(0, unavailable());
    await answer(1, snapshot());
    await waitFor(() => expect(hook.result.current.view?.seq).toBe(10));
    expect(hook.result.current.error).toBeNull();
  });

  it("shows an ended run's final state without connecting", async () => {
    stored = storedUpTo(40);
    const hook = renderHook(() => useLiveRun(RUN_ID));
    await answer(0, snapshot("finished"));
    await waitFor(() => expect(hook.result.current.ended).toBe("finished"));
    expect(hook.result.current.view?.seq).toBe(40);
    expect(hook.result.current.connection).toBe("closed");
    expect(clients).toHaveLength(0);
  });

  it("catches up when it connects, keeping the pushes that arrive meanwhile", async () => {
    stored = storedUpTo(10);
    const hook = renderHook(() => useLiveRun(RUN_ID));
    await answer(0, snapshot());
    await waitFor(() => expect(clients[0].started).toBe(1));
    act(() => clients[0].emit("connected"));
    await waitFor(() => expect(snapshotRequests).toHaveLength(2));
    stored = storedUpTo(12, [12]);
    act(() => {
      for (const seq of [11, 12, 13]) clients[0].receive(eventPush(seq, { key: seq >= 12 }));
    });
    await answer(1, snapshot());
    await waitFor(() => expect(hook.result.current.view?.seq).toBe(13));
    expect(keys(hook)).toEqual([12, 13]);
    expect(hook.result.current.connection).toBe("connected");
    expect(pushRequests).toEqual([0, 10]);
  });

  it("fetches what it missed after a gap without losing the pushes that arrive meanwhile", async () => {
    const hook = await connectedAt(10);
    stored = storedUpTo(12, [11]);
    act(() => clients[0].receive(eventPush(12))); // 11 was missed
    await waitFor(() => expect(snapshotRequests).toHaveLength(3));
    act(() => clients[0].receive(eventPush(13, { key: true }))); // newer than what's on its way
    await answer(2, snapshot());
    await waitFor(() => expect(hook.result.current.view?.seq).toBe(13));
    expect(keys(hook)).toEqual([11, 13]);
    expect(hook.result.current.state.events.map((e) => e.seq)).toEqual([11, 12, 13]);
  });

  it("catches up again after a reconnection", async () => {
    const hook = await connectedAt(10);
    act(() => clients[0].emit("disconnected"));
    expect(hook.result.current.connection).toBe("reconnecting");
    stored = storedUpTo(40, [33]);
    act(() => clients[0].emit("connected"));
    await answer(2, snapshot());
    await waitFor(() => expect(hook.result.current.view?.seq).toBe(40));
    expect(keys(hook)).toEqual([33]);
  });

  it("reads pushes sent as JSON text, the way the processor sends them", async () => {
    const hook = await connectedAt(10);
    act(() => clients[0].receive(JSON.stringify(eventPush(11, { key: true }))));
    await waitFor(() => expect(hook.result.current.view?.seq).toBe(11));
    expect(keys(hook)).toEqual([11]);
  });

  it("closes the connection when the run ends", async () => {
    const hook = await connectedAt(10);
    act(() => clients[0].receive(runEnd("finished")));
    await waitFor(() => expect(hook.result.current.ended).toBe("finished"));
    expect(clients[0].stopped).toBeGreaterThan(0);
  });

  it("keeps the page and tries again when a refetch fails", async () => {
    const hook = await connectedAt(10);
    act(() => clients[0].receive(eventPush(12))); // 11 was missed
    await respond(2, unavailable());
    await waitFor(() => expect(hook.result.current.trouble).toMatch(/HTTP 503/));
    expect(hook.result.current.error).toBeNull();
    expect(hook.result.current.view?.seq).toBe(10); // the page keeps what it has
    stored = storedUpTo(12);
    await answer(3, snapshot());
    await waitFor(() => expect(hook.result.current.view?.seq).toBe(12));
    expect(hook.result.current.trouble).toBeNull();
  });

  it("follows by polling when the push connection is refused", { timeout: 10_000 }, async () => {
    FakeClient.refuse = true; // the free tier's 21st connection, say
    stored = storedUpTo(10);
    const hook = renderHook(() => useLiveRun(RUN_ID));
    await answer(0, snapshot());
    await waitFor(() => expect(hook.result.current.connection).toBe("polling"));
    expect(hook.result.current.error).toBeNull();
    stored = storedUpTo(20);
    await respond(1, Response.json(snapshot()), 5_000); // the next poll
    await waitFor(() => expect(hook.result.current.view?.seq).toBe(20));
  });

  it("stops a client that connects after the page has let it go", async () => {
    stored = storedUpTo(10);
    const hook = renderHook(() => useLiveRun(RUN_ID));
    await answer(0, snapshot());
    await waitFor(() => expect(clients[0].started).toBe(1));
    hook.unmount();
    const stopped = clients[0].stopped;
    act(() => clients[0].emit("connected")); // the SDK ignores stop() while it connects
    expect(clients[0].stopped).toBe(stopped + 1);
    expect(snapshotRequests).toHaveLength(1);
  });

  it("keeps each card's earlier states when it loads after they changed", async () => {
    // A goal, then VAR ruling it out: the page loads after both, and a delayed screen needs the first.
    const goal = insightFixture("goal-e0532", { shown_seq: 11 });
    const ruledOut = { ...goal, flag: { reason: "Ruled out by VAR", event_id: "e0532", version: 1, seq: 12 }, shown_seq: 12, updated_at: "2026-10-20T12:01:00Z" };
    storedInsights = [
      { type: "insight", run_id: RUN_ID, rev: 1, insight: goal },
      { type: "insight", run_id: RUN_ID, rev: 2, insight: ruledOut },
    ];
    stored = storedUpTo(12);
    const hook = renderHook(() => useLiveRun(RUN_ID));
    await answer(0, { ...snapshot("finished"), insights: [ruledOut], insight_rev: 2 });
    await waitFor(() => expect(hook.result.current.state.history["goal-e0532"]).toHaveLength(2));
    expect(hook.result.current.state.history["goal-e0532"].map((i) => i.shown_seq)).toEqual([11, 12]);
    expect(hook.result.current.insights["goal-e0532"].flag?.seq).toBe(12);
  });

  it("lets a slow fetch finish while it polls", { timeout: 15_000 }, async () => {
    FakeClient.refuse = true;
    stored = storedUpTo(10);
    const hook = renderHook(() => useLiveRun(RUN_ID));
    await answer(0, snapshot());
    await waitFor(() => expect(hook.result.current.connection).toBe("polling"));
    stored = storedUpTo(20); // what the first poll's fetch brings, once its snapshot lands
    await waitFor(() => expect(snapshotRequests).toHaveLength(2), { timeout: 5_000 }); // the first poll
    // Slower than the next poll: the poll waits for it rather than starting over.
    await new Promise((resolve) => setTimeout(resolve, 3_500));
    expect(snapshotRequests).toHaveLength(2);
    await answer(1, snapshot());
    await waitFor(() => expect(hook.result.current.view?.seq).toBe(20));
  });

  it("stays closed when a run ends while the client is reconnecting", { timeout: 10_000 }, async () => {
    const hook = await connectedAt(10);
    act(() => clients[0].emit("disconnected"));
    await waitFor(() => expect(snapshotRequests).toHaveLength(3), { timeout: 5_000 }); // a poll
    await answer(2, snapshot("finished"));
    await waitFor(() => expect(hook.result.current.ended).toBe("finished"));
    const stopped = clients[0].stopped;
    act(() => clients[0].emit("connected")); // the SDK got its connection back after all
    expect(clients[0].stopped).toBe(stopped + 1);
    expect(hook.result.current.connection).toBe("closed");
    await new Promise((resolve) => setTimeout(resolve, 3_500));
    expect(snapshotRequests).toHaveLength(3); // no catching up, no polling
  });
});

describe("steady", () => {
  it("keeps what doesn't change during a run as the objects the page has", () => {
    const first = snapshot();
    const again = { ...snapshot(), run: { ...first.run }, match: { ...first.match }, insight_rev: 3 };
    const kept = steady(first, again);
    expect(kept.run).toBe(first.run);
    expect(kept.match).toBe(first.match);
    expect(kept.insight_rev).toBe(3);
    const other = { ...again, run: { ...again.run, run_id: "fedcba9876543210" } };
    expect(steady(first, other).run).toBe(other.run);
  });
});
