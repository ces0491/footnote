import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import RunPage from "./page";

vi.mock("@/components/live/live-run", () => ({ LiveRun: () => null }));

describe("RunPage", () => {
  it("has a heading that names the page for screen readers", () => {
    const props = { params: Promise.resolve({ runId: "0123456789abcdef" }), searchParams: Promise.resolve({}) } as PageProps<"/runs/[runId]">;
    expect(renderToStaticMarkup(<RunPage {...props} />)).toContain('<h1 class="sr-only">Replay of the showcase match</h1>');
  });
});
