// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Club, EventMessage, Insight, MatchMeta, RunDescriptor, RunSnapshot, SnapshotMessage } from "@/lib/live/contract";
import { initialRunViewState, runReducer } from "@/lib/live/run-reducer";
import { baseSnapshot, eventPush, insightFixture, runFixture } from "@/lib/live/test-fixtures";

import { LiveRun } from "./live-run";

// What the page's hooks would give it: the run as fetched, the clock, and a phone's screen.
const page = vi.hoisted(() => ({ live: null as unknown, now: 0 }));
vi.mock("@/hooks/use-live-run", () => ({ useLiveRun: () => page.live }));
vi.mock("@/hooks/use-now", () => ({ useNow: () => page.now }));
vi.mock("@/hooks/use-media-query", () => ({ useMediaQuery: () => false }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: () => {} }), usePathname: () => "/runs/0123456789abcdef" }));

const home: Club = { id: "sal", code: "SAL", name: "Saltmarsh Rovers", short_name: "Saltmarsh", colours: ["#1F7A6D", "#F4F1E8"], formation: "4-2-3-1" };
const away: Club = { id: "kin", code: "KIN", name: "Kingsferry Athletic", short_name: "Kingsferry", colours: ["#1B2A4A", "#E8A33D"], formation: "4-4-2" };
const match: MatchMeta = {
  match_id: "fl-2627-showcase-sal-kin",
  competition: "Footnote League",
  season: "2026/27",
  venue: "The Saltings",
  kickoff: "2027-03-07T13:00:00Z",
  referee: { id: "ref-06", name: "Louie Whinard" },
  home,
  away,
  lineups: [
    {
      club_id: "sal",
      formation: "4-2-3-1",
      attacking_direction: { first_half: "+x", second_half: "-x" },
      starters: [{ player_id: "sal-10", name: "Teo Varlan", shirt: 10, position: "AM" }],
      bench: [],
    },
    {
      club_id: "kin",
      formation: "4-4-2",
      attacking_direction: { first_half: "-x", second_half: "+x" },
      starters: [{ player_id: "kin-07", name: "Femi Adeyani", shirt: 7, position: "RW" }],
      bench: [],
    },
  ],
};

/** What useLiveRun gives a page that has the run's base, events and insights. */
function following(run: RunDescriptor, base: SnapshotMessage, events: EventMessage[], insights: Insight[]) {
  const state = runReducer(initialRunViewState, {
    kind: "resynced",
    pushes: [base, ...events],
    ended: null,
    backfillSeq: base.seq,
    insights,
    insightRev: insights.length,
  });
  const snapshot: RunSnapshot = {
    run,
    status: "running",
    producer: "auto",
    view: state.view,
    match,
    tracking: null,
    insights,
    insight_rev: insights.length,
    server_time: run.started_at,
  };
  return {
    receive: () => {},
    state,
    view: state.view,
    insights: state.insights,
    ended: null,
    snapshot,
    connection: "connected",
    error: null,
    trouble: null,
    latency: { p50: 240, p95: 306, samples: 66 },
    offset: 0,
  };
}

/** The wall time at which live play reaches replay second `replay`. */
const wall = (run: RunDescriptor, replay: number) => run.started_at + ((replay - run.start_replay) / run.speed) * 1000;

function card(headline: string, casual: string): Insight["card"] {
  return { headline, casual, analyst: "", plain: "", evidence: [], facts: [] };
}

afterEach(cleanup);

describe("Lucía joining at 60'", () => {
  // At 4x with her stream 20 seconds of match time behind live; the backfill ends at seq 10.
  const run = runFixture({ speed: 4, start_minute: 60, start_replay: 4012.59 });
  const base: SnapshotMessage = { ...baseSnapshot(10), phase: "second_half", score: { home: 1, away: 1 } };
  const events = Array.from({ length: 10 }, (_, i) =>
    eventPush(11 + i, { replay: run.start_replay + 1 + i, phase: "second_half", score: { home: 1, away: 1 } }),
  );
  const catchUp = insightFixture("catchup", {
    kind: "recap",
    topic: "catch_up",
    placement: "side_panel",
    duration: null,
    seq: 10,
    shown_seq: 10,
    card: card("What you missed, up to 59'", "Femi Adeyani scored at 23' and Teo Varlan levelled at 52'."),
    translations: {
      es: {
        headline: "Lo que te perdiste, hasta el minuto 59",
        casual: "Femi Adeyani marcó en el minuto 23 y Teo Varlan empató en el 52.",
        analyst: "",
      },
    },
  });
  const history = { live: false, status: "drafted" as const, status_by: null };
  const goal = insightFixture("goal-e0391", {
    ...history,
    seq: 5,
    shown_seq: 5,
    translations: { es: { headline: "Femi Adeyani anota", casual: "", analyst: "" } },
  });
  const spell = insightFixture("pressure-sal-1-2440", {
    ...history,
    kind: "segment",
    topic: "pressure",
    seq: 6,
    shown_seq: 6,
    at: { period: 1, t: 2624.55, minute: 44, added_minute: null },
    card: card("Saltmarsh pinning Kingsferry back", ""),
  });
  const chaos = insightFixture("chaos-2-1108", {
    kind: "segment",
    topic: "chaos",
    placement: "side_panel",
    duration: null,
    seq: 12,
    shown_seq: 12,
    card: card("Neither side in control", "No side has settled."),
    translations: { es: { headline: "Ninguno de los dos bandos tenía el control", casual: "Ningún equipo se ha asentado.", analyst: "" } },
  });
  const check = insightFixture("var-e0020", {
    kind: "rule_call",
    topic: "var_decision",
    seq: 13,
    shown_seq: 13,
    card: card("VAR: No penalty", "VAR checked the handball and gave no penalty."),
  });

  function watch(replay: number) {
    page.live = following(run, base, events, [catchUp, goal, spell, chaos, check]);
    page.now = wall(run, replay);
    render(<LiveRun runId={run.run_id} initialProfile="lucia" />);
  }

  it("gets the catch-up in Spanish beside the score, while her stream reaches the start", () => {
    watch(run.start_replay + 16);
    expect(screen.getByRole("region", { name: "Score" }).textContent).toContain("1–1");
    expect(screen.queryByRole("button", { name: /Show score/ })).toBeNull();
    const heading = screen.getByRole("heading", { name: "Lo que te perdiste, hasta el minuto 59" });
    expect(heading.getAttribute("lang")).toBe("es");
    expect(screen.getByText(/^Femi Adeyani marcó/).getAttribute("lang")).toBe("es");
    const joined = within(screen.getByText("Before you joined").parentElement!).getAllByRole("listitem");
    expect(joined.map((li) => [li.textContent, li.getAttribute("lang")])).toEqual([
      ["23'Femi Adeyani anota", "es"],
      ["44'Saltmarsh pinning Kingsferry back", null],
    ]);
    expect(screen.getByText(/it reaches the replay's start in 1 second\.$/)).toBeTruthy();
    // On a phone the measured latency would take much of the screen; it shows from the sm breakpoint.
    expect(screen.getByText(/^Publish to browser/).className.split(" ")).toEqual(expect.arrayContaining(["hidden", "sm:inline"]));
  });

  it("moves keyboard focus between the catch-up and the button that reopens it", () => {
    watch(run.start_replay + 16);
    fireEvent.click(screen.getByRole("button", { name: "Back to the match" }));
    const reopen = screen.getByRole("button", { name: /What you missed/ });
    expect(document.activeElement).toBe(reopen);
    fireEvent.click(reopen);
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Lo que te perdiste, hasta el minuto 59" }));
  });

  it("marks each card's language, and the English a card shows until it is translated", () => {
    watch(run.start_replay + 32); // her playback is at the replay's start plus 12
    const cards = within(screen.getByRole("list", { name: "Cards" }));
    const spanish = cards.getByText("Ninguno de los dos bandos tenía el control");
    expect(spanish.getAttribute("lang")).toBe("es");
    expect(cards.getByText("Ningún equipo se ha asentado.").getAttribute("lang")).toBe("es");
    expect(within(spanish.closest("li")!).queryByText("English")).toBeNull();
    const english = cards.getByText("VAR: No penalty");
    expect(english.getAttribute("lang")).toBeNull();
    expect(cards.getByText("VAR checked the handball and gave no penalty.").getAttribute("lang")).toBeNull();
    expect(within(english.closest("li")!).getByText("English")).toBeTruthy();
  });
});

describe("A replay the page can't follow", () => {
  it("says why, and offers a new replay rather than leaving the viewer at a dead end", () => {
    page.live = {
      receive: () => {},
      state: initialRunViewState,
      view: null,
      insights: {},
      ended: null,
      snapshot: null,
      connection: "polling",
      error: "There's no such replay.",
      trouble: null,
      latency: null,
      offset: 0,
    };
    render(<LiveRun runId="0123456789abcdef" initialProfile="sam" />);
    expect(screen.getByText("There's no such replay.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Start a new replay" }).getAttribute("href")).toBe("/");
    // Nothing is being followed, so nothing says it's connecting.
    expect(screen.queryByText(/Refreshing|Connecting|Live/)).toBeNull();
  });
});

describe("Nadia's preview of the world feed", () => {
  it("puts a goal on air when she approves it after the preview has passed the goal", () => {
    const run = runFixture({ speed: 4 }); // the goal's message, seq 15, was published at replay second 1305
    const goal = insightFixture("goal-e0015", {
      seq: 15,
      shown_seq: 15,
      status: "approved",
      status_by: "producer",
      status_at: new Date(wall(run, 1365)).toISOString(), // the agent's draft took a while
      source: "agent",
      agent_state: "done",
    });
    page.live = following(run, baseSnapshot(10), Array.from({ length: 10 }, (_, i) => eventPush(11 + i)), [goal]);
    page.now = wall(run, 1366);
    render(<LiveRun runId={run.run_id} initialProfile="nadia" />);
    expect(screen.getByText(/On air: Femi Adeyani scores\.$/)).toBeTruthy();
  });
});
