// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MatchMeta, TrackingLayout } from "@/lib/live/contract";
import type { Shown } from "@/lib/live/playback";
import { insightFixture, runFixture } from "@/lib/live/test-fixtures";

import { PitchView } from "./pitch-view";

// No tracking to fetch and no canvas to draw on: what's tested is drawn over the pitch.
vi.mock("@/hooks/use-tracking", () => ({ useTracking: () => () => null }));
vi.mock("./pitch-canvas", () => ({ PitchCanvas: () => null }));

const match = {
  home: { id: "sal", code: "SAL", name: "Saltmarsh Rovers", short_name: "Saltmarsh", colours: ["#1F7A6D", "#F4F1E8"], formation: "4-2-3-1" },
  away: { id: "kin", code: "KIN", name: "Kingsferry Athletic", short_name: "Kingsferry", colours: ["#1B2A4A", "#E8A33D"], formation: "4-4-2" },
  lineups: [],
} as unknown as MatchMeta;
const layout: TrackingLayout = { frame_rate: 10, frames_per_chunk: 100, values_per_frame: 46, frames: { "1": 30900, "2": 30000 }, slot_players: [] };
const run = runFixture();

function pitch(graphics: Shown[], waiting = 0, at = 1360) {
  render(
    <PitchView
      runId={run.run_id}
      run={run}
      match={match}
      layout={layout}
      position={() => ({ at, live: at + 3 })}
      graphics={graphics}
      mode="casual"
      calm={false}
      focus={null}
      waiting={waiting}
      caption="The match at 22:40 on your stream"
    />,
  );
}

afterEach(cleanup);

describe("PitchView", () => {
  it("marks a graphic in Spanish or French with its language, and leaves English to the page", () => {
    const goal = insightFixture("goal-e0391", {
      card: { headline: "Femi Adeyani anota", casual: "Kingsferry se adelanta.", analyst: "", plain: "", evidence: [], facts: [] },
    });
    const recap = insightFixture("ht", {
      kind: "recap",
      placement: "full_card",
      card: { headline: "Half-time", casual: "Kingsferry lead.", analyst: "", plain: "", evidence: [], facts: [] },
    });
    pitch([
      { insight: goal, from: 1357, lang: "es" },
      { insight: recap, from: 1357, lang: "en" },
    ]);
    expect(screen.getByText("Femi Adeyani anota").closest("[lang]")?.getAttribute("lang")).toBe("es");
    expect(screen.getByText("Kingsferry se adelanta.").closest("[lang]")?.getAttribute("lang")).toBe("es");
    expect(screen.getByText("Kingsferry lead.").closest("[lang]")).toBeNull();
  });

  it("leaves saying it's half-time to the recap when one is on air", () => {
    const recap = insightFixture("ht", {
      kind: "recap",
      topic: "half_time",
      placement: "full_card",
      card: { headline: "Half-time: Saltmarsh 0–1 Kingsferry", casual: "Kingsferry lead.", analyst: "", plain: "", evidence: [], facts: [] },
    });
    const breakTime = run.timeline.first_half_end + 12;
    pitch([], 0, breakTime);
    expect(screen.getByText("Half-time")).toBeTruthy();
    cleanup();
    pitch([{ insight: recap, from: breakTime - 5, lang: "en" }], 0, breakTime);
    expect(screen.queryByText("Half-time")).toBeNull();
    expect(screen.getByText("Half-time: Saltmarsh 0–1 Kingsferry")).toBeTruthy();
  });

  it("says how long the stream has to go before the replay's start", () => {
    pitch([], 0.75);
    expect(screen.getByText("The stream reaches the replay's start in 1 second.")).toBeTruthy();
  });
});
