// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { EventMessage, FeedEvent, MatchMeta } from "@/lib/live/contract";
import { roster } from "@/lib/live/describe";
import type { Detail, Pace } from "@/lib/live/described";
import type { Shown } from "@/lib/live/playback";
import { KICK_OFF_VIEW } from "@/lib/live/run-reducer";
import { eventPush, feedEventFixture, insightFixture } from "@/lib/live/test-fixtures";

import { DescribedFeed } from "./described-feed";

const club = (id: string, name: string, short: string) => ({ id, code: id.toUpperCase(), name, short_name: short, colours: ["#000", "#fff"] as [string, string], formation: "4-3-3" });
const player = (id: string, name: string) => ({ player_id: id, name, shirt: 1, position: "CM" });

// Saltmarsh attack towards x = 105 in the first half.
const MATCH: MatchMeta = {
  match_id: "m",
  competition: "Footnote League",
  season: "2026/27",
  venue: "The Saltings",
  kickoff: "2027-03-07T13:00:00Z",
  referee: { id: "ref", name: "Ref" },
  home: club("sal", "Saltmarsh Rovers", "Saltmarsh"),
  away: club("kin", "Kingsferry Athletic", "Kingsferry"),
  lineups: [
    {
      club_id: "sal",
      formation: "4-3-3",
      attacking_direction: { first_half: "+x", second_half: "-x" },
      starters: [player("sal-10", "Teo Varlan"), player("sal-09", "Marco Dellow")],
      bench: [],
    },
    { club_id: "kin", formation: "4-4-2", attacking_direction: { first_half: "-x", second_half: "+x" }, starters: [], bench: [] },
  ],
};
const R = roster(MATCH);

const push = (seq: number, event: Partial<FeedEvent>, extra: Partial<EventMessage> = {}) => eventPush(seq, { event: feedEventFixture(seq, event), ...extra });

// An interception (standard detail), a pass across (full), then a shot and the goal (key moments).
const EVENTS = [
  push(1, { type: "possession_change", team_id: "sal", cause: "interception", x: 60, y: 50 }),
  push(2, { type: "pass", team_id: "sal", player_id: "sal-10", recipient_id: "sal-09", outcome: "complete", pass_type: "open_play", length: 8, x: 60, y: 30, end_x: 62, end_y: 38 }),
  push(3, { type: "shot", team_id: "sal", player_id: "sal-09", body_part: "right_foot", distance: 19.4, outcome: "goal" }),
  push(4, { type: "goal", team_id: "sal", player_id: "sal-09", own_goal: false }, { score: { home: 1, away: 0 } }),
];
const SHOT = "Dellow shoots with the right foot from 19 metres: goal.";
const GOAL = "Goal for Saltmarsh, scored by Dellow. Saltmarsh 1, Kingsferry 0.";

interface Props {
  events: EventMessage[];
  reached: number;
  cards: Shown[];
  detail: Detail;
  pace: Pace;
}

function feed({ events = EVENTS, reached = 0, cards = [], detail = "standard", pace = "normal" }: Partial<Props> = {}) {
  return (
    <DescribedFeed
      match={MATCH}
      roster={R}
      base={KICK_OFF_VIEW}
      startReplay={1290}
      events={events}
      reached={reached}
      cards={cards}
      detail={detail}
      pace={pace}
      onDetail={() => {}}
      onPace={() => {}}
    />
  );
}

/** What the live region holds: what the screen reader was last given to say. */
const region = () => document.querySelector('[aria-live="polite"]')!;
const said = () => region().textContent?.trim();
const tick = (ms: number) =>
  act(() => {
    vi.advanceTimersByTime(ms);
  });

const card = (plain: string) => ({ headline: "Dellow scores", casual: "", analyst: "", plain, evidence: [], facts: [] });
const TEMPLATE = insightFixture("goal-e0004", { version: 1, source: "template", card: card("Marco Dellow scores. Saltmarsh lead 1-0.") });
const AGENT = insightFixture("goal-e0004", { version: 2, source: "agent", card: card("Dellow finishes a quick move. Saltmarsh lead 1-0.") });

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("DescribedFeed", () => {
  it("says an announcement worded like the one before it again", () => {
    // Three runs with the ball that read the same, one to each announcement, at full detail and quick pace.
    const run = (seq: number) => push(seq, { type: "carry", team_id: "sal", player_id: "sal-10", x: 40, y: 34, end_x: 66, end_y: 34 });
    const events = [run(1), run(2), run(3)];
    const view = render(feed({ events, detail: "full", pace: "quick" }));
    const heard: string[] = [];
    for (const reached of [1, 2, 3]) {
      view.rerender(feed({ events, reached, detail: "full", pace: "quick" }));
      tick(1500);
      heard.push(region().textContent ?? "");
    }
    expect(heard.map((h) => h.trim())).toEqual(Array(3).fill("Varlan runs with the ball, in the opposition half."));
    // Each is a change to the live region, which is what makes a screen reader speak.
    expect(heard[1]).not.toBe(heard[0]);
    expect(heard[2]).not.toBe(heard[1]);
  });

  it("keeps the lines waiting to be said when the listener changes the detail", () => {
    const view = render(feed({ reached: 1 }));
    view.rerender(feed({ reached: 4 })); // the pass, the shot and the goal reach playback
    view.rerender(feed({ reached: 4, detail: "key" })); // and the detail changes before the next announcement
    tick(4000);
    expect(said()).toBe(`${SHOT} ${GOAL}`);
  });

  it("counts the lines a fuller detail adds to what is there as said", () => {
    const view = render(feed({ reached: 1 }));
    view.rerender(feed({ reached: 3 })); // the pass across, which only full detail tells, and the shot
    view.rerender(feed({ reached: 3, detail: "full" }));
    tick(4000);
    expect(said()).toBe(SHOT);
  });

  it("reads a graphic once, in the wording it has when its turn comes", () => {
    const view = render(feed({ reached: 4 }));
    view.rerender(feed({ reached: 4, cards: [{ insight: TEMPLATE, from: 1294 }] }));
    tick(4000);
    expect(said()).toBe("On screen: Marco Dellow scores. Saltmarsh lead 1-0.");
    // The agent's wording replaces the template's after the listener heard it.
    const before = region().textContent;
    view.rerender(feed({ reached: 4, cards: [{ insight: AGENT, from: 1294 }] }));
    tick(4000);
    expect(region().textContent).toBe(before);
    // The list shows the wording as it now stands.
    expect(screen.getAllByRole("listitem")[0].textContent).toBe("On screen: Dellow finishes a quick move. Saltmarsh lead 1-0.");
  });

  it("reads a graphic not yet read in its latest wording, and not again for a translation", () => {
    const view = render(feed({ reached: 4 }));
    view.rerender(feed({ reached: 4, cards: [{ insight: TEMPLATE, from: 1294 }] }));
    view.rerender(feed({ reached: 4, cards: [{ insight: AGENT, from: 1294 }] }));
    tick(4000);
    expect(said()).toBe("On screen: Dellow finishes a quick move. Saltmarsh lead 1-0.");
    const before = region().textContent;
    const spanish = { ...AGENT, card: card("Dellow culmina una jugada rápida. El Saltmarsh gana 1-0.") };
    view.rerender(feed({ reached: 4, cards: [{ insight: spanish, from: 1294, lang: "es" }] }));
    tick(4000);
    expect(region().textContent).toBe(before);
  });

  it("marks a graphic's Spanish wording with its language, in what is said and in the list", () => {
    const spanish = insightFixture("goal-e0004", { card: card("Marco Dellow marca. El Saltmarsh se adelanta 1-0.") });
    const view = render(feed({ reached: 4 }));
    view.rerender(feed({ reached: 4, cards: [{ insight: spanish, from: 1294, lang: "es" }] }));
    tick(4000);
    expect(said()).toBe("On screen: Marco Dellow marca. El Saltmarsh se adelanta 1-0.");
    expect(region().querySelector('[lang="es"]')?.textContent).toBe("Marco Dellow marca. El Saltmarsh se adelanta 1-0.");
    const [item] = screen.getAllByRole("listitem");
    expect(item.querySelector('[lang="es"]')?.textContent).toBe("Marco Dellow marca. El Saltmarsh se adelanta 1-0.");
    // "On screen:" and the event lines stay in the page's English.
    expect(document.querySelectorAll("[lang]")).toHaveLength(2);
  });

  it("labels the pause button with what it does now, without a pressed state", () => {
    render(feed());
    const pause = screen.getByRole("button", { name: "Pause" });
    expect(pause.hasAttribute("aria-pressed")).toBe(false);
    fireEvent.click(pause);
    expect(screen.getByRole("button", { name: "Resume" }).hasAttribute("aria-pressed")).toBe(false);
  });

  it("reads back each line with its clock, in a list the keyboard can scroll", () => {
    render(feed({ reached: 4 }));
    const list = screen.getByRole("list", { name: "The match so far, latest first" });
    expect(list.tabIndex).toBe(0);
    const [latest] = screen.getAllByRole("listitem");
    expect(latest.textContent).toBe(`21:34${GOAL}`);
    expect(latest.querySelector("[aria-hidden]")).toBeNull();
  });
});
