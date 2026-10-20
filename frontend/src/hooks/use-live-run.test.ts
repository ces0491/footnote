// @vitest-environment jsdom
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { EventMessage, MatchMeta, PushMessage, RunDescriptor, RunSnapshot, RunStatus } from "@/lib/live/contract";

import { useLiveRun } from "./use-live-run";

// A stand-in for the Web PubSub client: the tests decide when it connects and what it receives.
const { FakeClient, clients } = vi.hoisted(() => {
  type Handler = (e: unknown) => void;
  const clients: InstanceType<typeof FakeClient>[] = [];
  class FakeClient {
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
    }
    stop() {
      this.stopped += 1;
    }
  }
  return { FakeClient, clients };
});
vi.mock("@azure/web-pubsub-client", () => ({ WebPubSubClient: FakeClient }));

const RUN_ID = "0123456789abcdef";

// Snapshot requests wait until a test answers them, so it controls what arrives first.
let snapshotRequests: ((response: Response) => void)[] = [];

function fetchStub(input: RequestInfo | URL): Promise<Response> {
  const url = String(input);
  if (url === "/api/time") return Promise.resolve(Response.json({ now: Date.now() }));
  if (url.endsWith("/negotiate")) return Promise.resolve(Response.json({ url: "wss://example.test/client" }));
  return new Promise((resolve) => snapshotRequests.push(resolve));
}

function shot(seq: number) {
  return { seq, event_id: `e${seq}`, version: 1, type: "shot", period: 1, t: seq, clock: seq, minute: 1, added_minute: null };
}

function snapshot(seq: number, status: RunStatus = "running", keySeqs: number[] = []): RunSnapshot {
  return {
    run: { run_id: RUN_ID } as RunDescriptor,
    status,
    view: { seq, phase: "first_half", clock: null, score: { home: 0, away: 0 }, teams: {}, key_events: keySeqs.map(shot) },
    match: {} as MatchMeta,
    insights: [],
    insight_rev: 0,
    server_time: Date.now(),
  };
}

function event(seq: number, key = false): EventMessage {
  const live = { seq, phase: "first_half" as const, clock: null, score: { home: 0, away: 0 }, teams: {} };
  return { type: "event", run_id: RUN_ID, event: shot(seq), key, ...live, timing: {} };
}

const runEnd = (reason: "finished"): PushMessage => ({ type: "run_end", run_id: RUN_ID, reason, timing: {} });

async function respond(index: number, response: Response) {
  await waitFor(() => expect(snapshotRequests.length).toBeGreaterThan(index), { timeout: 3_000 });
  await act(async () => snapshotRequests[index](response));
}

const answer = (index: number, value: RunSnapshot) => respond(index, Response.json(value));

/** Render the hook and bring it to a live, connected state at `seq`. */
async function connectedAt(seq: number) {
  const hook = renderHook(() => useLiveRun(RUN_ID));
  await answer(0, snapshot(seq));
  await waitFor(() => expect(clients[0].started).toBe(1));
  act(() => clients[0].emit("connected"));
  await answer(1, snapshot(seq));
  await waitFor(() => expect(hook.result.current.view?.seq).toBe(seq));
  return hook;
}

const keys = (hook: { result: { current: ReturnType<typeof useLiveRun> } }) =>
  hook.result.current.view?.key_events.map((e) => e.seq);

beforeEach(() => {
  snapshotRequests = [];
  clients.length = 0;
  vi.stubGlobal("fetch", vi.fn(fetchStub));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("useLiveRun", () => {
  it("waits while the run is starting, then shows it", async () => {
    const hook = renderHook(() => useLiveRun(RUN_ID));
    await respond(0, Response.json({ status: "starting" }, { status: 202 }));
    await answer(1, snapshot(10));
    await waitFor(() => expect(hook.result.current.view?.seq).toBe(10));
    expect(hook.result.current.error).toBeNull();
  });

  it("says so when there is no such run", async () => {
    const hook = renderHook(() => useLiveRun(RUN_ID));
    await respond(0, Response.json({ error: "no such run" }, { status: 404 }));
    await waitFor(() => expect(hook.result.current.error).toBe("There's no such replay."));
    expect(clients[0].started).toBe(0);
  });

  it("shows an ended run's final state without connecting", async () => {
    const hook = renderHook(() => useLiveRun(RUN_ID));
    await answer(0, snapshot(1819, "finished"));
    await waitFor(() => expect(hook.result.current.ended).toBe("finished"));
    expect(hook.result.current.view?.seq).toBe(1819);
    expect(hook.result.current.connection).toBe("closed");
    expect(clients[0].started).toBe(0);
  });

  it("catches up when it connects, keeping the pushes that arrive meanwhile", async () => {
    const hook = renderHook(() => useLiveRun(RUN_ID));
    await answer(0, snapshot(10));
    await waitFor(() => expect(clients[0].started).toBe(1));
    act(() => clients[0].emit("connected"));
    await waitFor(() => expect(snapshotRequests).toHaveLength(2));
    act(() => {
      for (const seq of [11, 12, 13]) clients[0].receive(event(seq, seq === 13));
    });
    await answer(1, snapshot(12, "running", [12]));
    await waitFor(() => expect(hook.result.current.view?.seq).toBe(13));
    expect(keys(hook)).toEqual([12, 13]);
    expect(hook.result.current.connection).toBe("connected");
    expect(snapshotRequests).toHaveLength(2);
  });

  it("refetches after a missed push without losing the pushes that arrive meanwhile", async () => {
    const hook = await connectedAt(10);
    act(() => clients[0].receive(event(12))); // 11 was missed
    await waitFor(() => expect(snapshotRequests).toHaveLength(3));
    act(() => clients[0].receive(event(13, true))); // newer than the snapshot on its way
    await answer(2, snapshot(12, "running", [11]));
    await waitFor(() => expect(hook.result.current.view?.seq).toBe(13));
    expect(keys(hook)).toEqual([11, 13]);
  });

  it("catches up again after a reconnection", async () => {
    const hook = await connectedAt(10);
    act(() => clients[0].emit("disconnected"));
    expect(hook.result.current.connection).toBe("reconnecting");
    act(() => clients[0].emit("connected"));
    await answer(2, snapshot(40, "running", [33]));
    await waitFor(() => expect(hook.result.current.view?.seq).toBe(40));
    expect(keys(hook)).toEqual([33]);
  });

  it("reads pushes sent as JSON text, the way the processor sends them", async () => {
    const hook = await connectedAt(10);
    act(() => clients[0].receive(JSON.stringify(event(11, true))));
    await waitFor(() => expect(hook.result.current.view?.seq).toBe(11));
    expect(keys(hook)).toEqual([11]);
  });

  it("closes the connection when the run ends", async () => {
    const hook = await connectedAt(10);
    act(() => clients[0].receive(runEnd("finished")));
    await waitFor(() => expect(hook.result.current.ended).toBe("finished"));
    expect(clients[0].stopped).toBeGreaterThan(0);
  });
});
