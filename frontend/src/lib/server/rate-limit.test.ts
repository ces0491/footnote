import { describe, expect, it, vi } from "vitest";

// server-only throws when imported outside a React Server Component build.
vi.mock("server-only", () => ({}));

import { allowStart, clientAddress } from "./rate-limit";

describe("clientAddress", () => {
  it("takes the last X-Forwarded-For entry, the one the ingress added", () => {
    expect(clientAddress(new Headers({ "x-forwarded-for": "203.0.113.9" }))).toBe("203.0.113.9");
    expect(clientAddress(new Headers({ "x-forwarded-for": "198.51.100.1, 203.0.113.9" }))).toBe("203.0.113.9");
  });

  it("falls back when the header is missing", () => {
    expect(clientAddress(new Headers())).toBe("unknown");
  });
});

describe("allowStart", () => {
  it("allows eight starts per address in five minutes", () => {
    const t0 = 1_800_000_000_000;
    const allowed = Array.from({ length: 9 }, (_, i) => allowStart("192.0.2.1", t0 + i));
    expect(allowed).toEqual([true, true, true, true, true, true, true, true, false]);
    expect(allowStart("192.0.2.2", t0 + 10)).toBe(true);
    expect(allowStart("192.0.2.1", t0 + 5 * 60_000 + 1)).toBe(true);
  });
});
