import { describe, expect, it, vi } from "vitest";

// server-only throws when imported outside a React Server Component build.
vi.mock("server-only", () => ({}));

import { clientAddress, Limit, negotiations, starts } from "./rate-limit";

describe("clientAddress", () => {
  it("takes the last X-Forwarded-For entry, the one the ingress added", () => {
    expect(clientAddress(new Headers({ "x-forwarded-for": "203.0.113.9" }))).toBe("203.0.113.9");
    expect(clientAddress(new Headers({ "x-forwarded-for": "198.51.100.1, 203.0.113.9" }))).toBe("203.0.113.9");
  });

  it("falls back when the header is missing", () => {
    expect(clientAddress(new Headers())).toBe("unknown");
  });
});

describe("Limit", () => {
  it("counts each address in its own window, and says when the window ends", () => {
    const limit = new Limit(60_000, 2);
    const t0 = 1_800_000_000_000;
    expect([limit.allow("192.0.2.1", t0), limit.allow("192.0.2.1", t0 + 1), limit.allow("192.0.2.1", t0 + 2)]).toEqual([true, true, false]);
    expect(limit.allow("192.0.2.2", t0 + 3)).toBe(true);
    expect(limit.retryAfter("192.0.2.1", t0 + 30_000)).toBe(30);
    expect(limit.allow("192.0.2.1", t0 + 60_001)).toBe(true);
  });
});

describe("starts", () => {
  it("allows eight starts per address in five minutes", () => {
    const t0 = 1_800_000_000_000;
    const allowed = Array.from({ length: 9 }, (_, i) => starts.allow("192.0.2.1", t0 + i));
    expect(allowed).toEqual([true, true, true, true, true, true, true, true, false]);
    expect(starts.allow("192.0.2.2", t0 + 10)).toBe(true);
    expect(starts.allow("192.0.2.1", t0 + 5 * 60_000 + 1)).toBe(true);
  });
});

describe("negotiations", () => {
  it("allows sixty connection URLs per address in five minutes", () => {
    const t0 = 1_800_000_000_000;
    const allowed = Array.from({ length: 61 }, (_, i) => negotiations.allow("198.51.100.7", t0 + i));
    expect(allowed.filter(Boolean)).toHaveLength(60);
    expect(allowed.at(-1)).toBe(false);
    expect(negotiations.retryAfter("198.51.100.7", t0 + 61)).toBe(300);
  });
});
