import { describe, expect, it } from "vitest";

import { clubColour, contrast, GROUND, inkOn } from "./club-colour";
import type { Club } from "./live/contract";

const club = (colours: [string, string]): Club => ({ id: "x", code: "X", name: "X", short_name: "X", colours, formation: "4-4-2" });

describe("clubColour", () => {
  it("shows Kingsferry in amber: their navy all but vanishes on the dark ground", () => {
    expect(contrast("#1B2A4A", GROUND)).toBeLessThan(1.5);
    expect(clubColour(club(["#1B2A4A", "#E8A33D"]))).toBe("#E8A33D");
  });

  it("lightens Saltmarsh's teal until it reads, rather than showing their cream", () => {
    const teal = clubColour(club(["#1F7A6D", "#F4F1E8"]));
    expect(teal).not.toBe("#F4F1E8");
    expect(contrast(teal, GROUND)).toBeGreaterThanOrEqual(3);
    expect(contrast(teal, GROUND)).toBeLessThan(3.6); // no lighter than it needs to be
  });

  it("keeps a first colour that already reads", () => {
    expect(clubColour(club(["#E03A3E", "#FFFFFF"]))).toBe("#E03A3E");
  });
});

describe("inkOn", () => {
  it("puts dark ink on amber and light ink on navy", () => {
    expect(inkOn("#E8A33D")).toBe("#0d141e");
    expect(inkOn("#1B2A4A")).toBe("#f1f4f7");
  });
});
