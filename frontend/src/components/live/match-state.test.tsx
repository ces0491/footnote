// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { Club, MatchState, StateSpell, TeamStats } from "@/lib/live/contract";

import { MatchStatePanel, stateLine } from "./match-state";
import { StatsPanel } from "./stats-panel";

const home = { id: "sal", code: "SAL", name: "Saltmarsh Rovers", short_name: "Saltmarsh", colours: ["#1F7A6D", "#F4F1E8"], formation: "4-2-3-1" } as Club;
const away = { id: "kin", code: "KIN", name: "Kingsferry Athletic", short_name: "Kingsferry", colours: ["#1B2A4A", "#E8A33D"], formation: "4-4-2" } as Club;

afterEach(cleanup);

describe("MatchStatePanel", () => {
  const state: MatchState = { period: 1, second: 1421, state: "control", team_id: "sal", confidence: 0.71, on_top: { home: 0.62, away: 0.21 } };
  const timeline: StateSpell[] = [
    { period: 1, state: "balanced", team_id: null, start: 0, end: 80 },
    { period: 1, state: "control", team_id: "sal", start: 85, end: 1300 },
    { period: 1, state: "transition", team_id: "kin", start: 1340, end: 1356 },
    { period: 2, state: "chaos", team_id: null, start: 1080, end: 1380 },
  ];

  it("says which side is on top, how sure the model is and how far behind play it runs", () => {
    render(<MatchStatePanel home={home} away={away} state={state} timeline={timeline} />);
    expect(screen.getByText("Saltmarsh in control")).toBeTruthy();
    expect(screen.getByText("71% likely")).toBeTruthy();
    expect(screen.getByText(/as of 23:41/)).toBeTruthy();
    expect(screen.getByRole("img", { name: /Saltmarsh 62%, Kingsferry 21%/ })).toBeTruthy();
  });

  it("gives screen readers the timeline as text", () => {
    render(<MatchStatePanel home={home} away={away} state={state} timeline={timeline} />);
    const items = screen.getAllByRole("listitem").map((li) => li.textContent);
    expect(items).toContain("22:20 to 22:36: Kingsferry on the break");
    expect(items).toContain("63:00 to 68:00: Neither side in control");
  });

  it("waits for the first estimate", () => {
    render(<MatchStatePanel home={home} away={away} state={null} timeline={[]} />);
    expect(screen.getByText(/first estimate comes a few seconds after kick-off/)).toBeTruthy();
  });

  it("names every state in plain words", () => {
    expect(stateLine("pressure", home, away)).toBe("Saltmarsh pinning Kingsferry back");
    expect(stateLine("balanced", null, null)).toBe("Evenly matched");
  });
});

describe("StatsPanel", () => {
  const stats = (extra: Partial<TeamStats>): TeamStats => ({
    shots: 5,
    on_target: 2,
    passes: 300,
    passes_completed: 250,
    corners: 3,
    fouls: 8,
    offsides: 1,
    yellow_cards: 1,
    red_cards: 0,
    pass_accuracy: 0.833,
    possession: 0.6,
    ...extra,
  });

  it("shows the modelled and tracked figures, and a dash where there are none yet", () => {
    const h = stats({ pass_length: 17.6, pass_difficulty: 0.21, distance_km: 54.3, top_shot_kmh: 97.4 });
    const a = stats({ pass_length: 21.2, pass_difficulty: 0.27, distance_km: 55.1, top_shot_kmh: null });
    render(<StatsPanel home={home} away={away} stats={{ sal: h, kin: a }} />);
    expect(screen.getByText("0.21")).toBeTruthy();
    expect(screen.getByText("54.3 km")).toBeTruthy();
    expect(screen.getByText("97 km/h")).toBeTruthy();
    expect(screen.getByText("Fastest shot").closest("div")?.textContent).toContain("–");
  });
});
