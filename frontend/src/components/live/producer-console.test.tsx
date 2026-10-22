// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { Insight } from "@/lib/live/contract";
import type { Roster } from "@/lib/live/describe";
import { insightFixture } from "@/lib/live/test-fixtures";

import { ProducerConsole } from "./producer-console";

const roster: Roster = { player: () => undefined, clubName: () => "" };

afterEach(cleanup);

/** The console's Corrections alert, with `insights` as the run's cards. */
function corrections(insights: Insight[]) {
  render(
    <ProducerConsole
      runId="0123456789abcdef"
      insights={Object.fromEntries(insights.map((i) => [i.insight_id, i]))}
      clock={null}
      roster={roster}
      viewer="00000000-0000-4000-8000-000000000000"
      canProduce
      mode="manual"
      onMode={async () => null}
      onChange={() => {}}
    />,
  );
  return within(screen.getByRole("alert"));
}

describe("ProducerConsole corrections", () => {
  it("shows the wording a correction restated, where it came from and its evidence, beside the reason", () => {
    const restated = insightFixture("goal-e1586", {
      seq: 1620,
      shown_seq: 1620,
      flag: { reason: "The data provider amended the goal this cites", event_id: "e1619", version: 2, seq: 1620 },
      status: "drafted",
      status_by: "correction",
      source: "agent",
      agent_state: "done",
      card: {
        headline: "Femi Adeyani scores",
        casual: "Kingsferry lead late on through Femi Adeyani.",
        analyst: "The shot was from 21 m.",
        plain: "",
        evidence: ["e1585", "e1586"],
        facts: [],
      },
    });
    const entry = within(corrections([restated]).getByText("Femi Adeyani scores").closest("li")!);
    expect(entry.getByText(/The data provider amended the goal this cites/)).toBeTruthy();
    expect(entry.getByText("Kingsferry lead late on through Femi Adeyani.")).toBeTruthy();
    expect(entry.getByText("The shot was from 21 m.")).toBeTruthy();
    expect(entry.getByText("Corrected: needs approval again")).toBeTruthy();
    expect(entry.getByText("Agent")).toBeTruthy();
    expect(entry.getByRole("button", { name: "Evidence (2 events)" })).toBeTruthy();
    expect(entry.getByRole("button", { name: "Agent runs" })).toBeTruthy();
    expect(entry.getByRole("button", { name: "Approve" })).toBeTruthy();
  });

  it("keeps a card VAR undid to its headline and the reason", () => {
    const ruledOut = insightFixture("goal-e0532", {
      seq: 533,
      shown_seq: 535,
      flag: { reason: "Ruled out by VAR", event_id: "e0534", version: 1, seq: 535 },
      card: { headline: "Marco Dellow scores", casual: "Saltmarsh level.", analyst: "", plain: "", evidence: ["e0532"], facts: [] },
    });
    const entry = within(corrections([ruledOut]).getByText("Marco Dellow scores").closest("li")!);
    expect(entry.getByText(/Ruled out by VAR/)).toBeTruthy();
    expect(entry.queryByText("Saltmarsh level.")).toBeNull();
  });
});
