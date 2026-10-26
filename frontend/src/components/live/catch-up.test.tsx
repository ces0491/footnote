// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { Roster } from "@/lib/live/describe";
import type { Language } from "@/lib/live/language";
import { insightFixture } from "@/lib/live/test-fixtures";

import { CatchUp } from "./catch-up";

const roster: Roster = { player: () => undefined, clubName: () => "" };
const insight = insightFixture("catchup", {
  card: { headline: "What you missed, up to 59'", casual: "Kingsferry lead.", analyst: "", plain: "", evidence: [], facts: [] },
});

afterEach(cleanup);

function catchUp(lang: Language, reading: Language) {
  return (
    <CatchUp runId="0123456789abcdef" insight={insight} lang={lang} reading={reading} moments={[]} analyst={false} onClose={() => {}} roster={roster} />
  );
}

describe("CatchUp", () => {
  it("marks wording still in English for a fan reading Spanish, as the panel's graphics are", () => {
    render(catchUp("en", "es"));
    expect(screen.getByText("English").getAttribute("title")).toBe("Not yet in Español: the English for now");
  });

  it("marks nothing once it is translated, or for a fan reading English", () => {
    const view = render(catchUp("es", "es"));
    expect(screen.queryByText("English")).toBeNull();
    view.rerender(catchUp("en", "en"));
    expect(screen.queryByText("English")).toBeNull();
  });
});
