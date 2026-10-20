// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";

import { viewerIdPattern } from "./contract";
import { viewerId } from "./viewer";

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("viewerId", () => {
  it("keeps one ID for the browser", () => {
    const id = viewerId();
    expect(id).toMatch(viewerIdPattern);
    expect(viewerId()).toBe(id);
    expect(localStorage.getItem("footnote.viewer")).toBe(id);
  });

  it("replaces a stored value that isn't an ID", () => {
    localStorage.setItem("footnote.viewer", "not an id");
    expect(viewerId()).toMatch(viewerIdPattern);
  });

  it("keeps an ID for the page where storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    const id = viewerId();
    expect(id).toMatch(viewerIdPattern);
    expect(viewerId()).toBe(id);
  });
});
