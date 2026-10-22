// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { FeedEvent, MatchMeta } from "@/lib/live/contract";
import { roster } from "@/lib/live/describe";

import { Ticker } from "./ticker";

const match = {
  home: { id: "sal", short_name: "Saltmarsh" },
  away: { id: "kin", short_name: "Kingsferry" },
  lineups: [
    { club_id: "sal", starters: [{ player_id: "sal-04", name: "Jory Penhallow", shirt: 4, position: "CB" }], bench: [] },
    { club_id: "kin", starters: [{ player_id: "kin-07", name: "Femi Adeyani", shirt: 7, position: "RW" }], bench: [] },
  ],
} as unknown as MatchMeta;
const r = roster(match);

// The showcase's 81st-minute goal, first given as a Penhallow own goal, and the provider's amendment at 84'.
const GOAL: FeedEvent = { seq: 1580, event_id: "e1586", version: 1, type: "goal", period: 2, t: 2110, clock: 4810, minute: 81, added_minute: null, team_id: "kin", player_id: "sal-04", own_goal: true };
const AMENDMENT: FeedEvent = {
  seq: 1620,
  event_id: "e1586",
  version: 2,
  type: "amendment",
  period: 2,
  t: 2300,
  clock: 5000,
  minute: 84,
  added_minute: null,
  amends: "goal",
  changes: { player_id: { before: "sal-04", after: "kin-07" }, own_goal: { before: true, after: false } },
  corrected_event: { event_id: "e1586", minute: 81, added_minute: null, own_goal: false },
};

afterEach(cleanup);

describe("Ticker", () => {
  it("marks a goal the provider corrected later, and lists the correction", () => {
    render(<Ticker events={[GOAL, AMENDMENT]} tags={[]} roster={r} />);
    const [correction, goal] = screen.getAllByRole("listitem"); // latest first
    expect(correction.textContent).toBe("84'Correction: the 81' goal is now credited to Femi Adeyani; it had been given as an own goal by Jory Penhallow");
    expect(goal.textContent).toBe("81'Goal, Kingsferry: own goal by Jory PenhallowCorrected by the data provider at 84'");
  });

  it("leaves a goal unmarked until the correction reaches the list", () => {
    render(<Ticker events={[GOAL]} tags={[]} roster={r} />);
    expect(screen.getByRole("listitem").textContent).toBe("81'Goal, Kingsferry: own goal by Jory Penhallow");
  });

  it("marks a goal VAR ruled out, once the decision reaches the list", () => {
    // The showcase's 31st-minute goal, ruled out for offside at 33'.
    const goal: FeedEvent = { ...GOAL, seq: 533, event_id: "e0532", period: 1, minute: 31, team_id: "sal", player_id: "sal-04", own_goal: false };
    const decision: FeedEvent = {
      seq: 535,
      event_id: "e0534",
      version: 1,
      type: "var_check",
      period: 1,
      t: 1980,
      clock: 1980,
      minute: 33,
      added_minute: null,
      status: "complete",
      check: "goal",
      decision: "no_goal",
      overturned: true,
      goal_event_id: "e0532",
    };
    render(<Ticker events={[goal]} tags={[]} roster={r} />);
    expect(screen.getByRole("listitem").textContent).toBe("31'Goal, Saltmarsh: Jory Penhallow");
    cleanup();
    render(<Ticker events={[goal, decision]} tags={[]} roster={r} />);
    const [ruling, ruledOut] = screen.getAllByRole("listitem");
    expect(ruling.textContent).toBe("33'VAR: no goal, decision overturned");
    expect(ruledOut.textContent).toBe("31'Goal, Saltmarsh: Jory PenhallowRuled out by VAR at 33'");
    expect(ruledOut.className).not.toContain("bg-emerald-50");
  });

  it("lets the keyboard scroll the list", () => {
    render(<Ticker events={[GOAL]} tags={[]} roster={r} />);
    expect(screen.getByRole("list", { name: "Key moments, latest first" }).tabIndex).toBe(0);
  });
});
