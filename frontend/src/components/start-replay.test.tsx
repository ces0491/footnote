// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { hydrateRoot } from "react-dom/client";
import { renderToString } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StartReplay } from "./start-replay";

const push = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

afterEach(() => {
  cleanup();
  push.mockReset();
  vi.unstubAllGlobals();
});

/** A fetch that answers once `answer` is called, so a test can look at the page while it waits. */
function pendingFetch() {
  let answer: (response: Response) => void = () => {};
  const fetch = vi.fn(() => new Promise<Response>((resolve) => (answer = resolve)));
  vi.stubGlobal("fetch", fetch);
  return { fetch, answer: (status: number, body: object) => answer(Response.json(body, { status })) };
}

const startButton = () => screen.getByRole("button", { name: /Start|Starting|Loading/ }) as HTMLButtonElement;

describe("StartReplay", () => {
  it("labels each jump point with what happens there and the viewers who show it best", () => {
    render(<StartReplay />);
    const jumps = within(screen.getByRole("radiogroup", { name: "Start from" })).getAllByRole("radio");
    expect(jumps.map((j) => j.getAttribute("aria-label"))).toEqual([
      "Kick-off, The whole match",
      "23', Kingsferry score, Nadia, then Sam",
      "31', A goal VAR rules out, Tom's described feed",
      "60', Join late, Lucía, in Spanish",
      "81', The amended goal, Nadia's corrections",
    ]);
  });

  it("starts as Sam, from 23', at 2x", () => {
    render(<StartReplay />);
    const checked = (group: string) =>
      within(screen.getByRole("radiogroup", { name: group }))
        .getAllByRole("radio")
        .filter((r) => r.getAttribute("aria-checked") === "true")
        .map((r) => r.textContent);
    expect(checked("Watch as")).toEqual([expect.stringMatching(/^SamFan/)]); // the name, then the role under it
    expect(checked("Start from")).toEqual(["23'Kingsferry scoreNadia, then Sam"]);
    expect(checked("Speed")).toEqual(["2×"]);
  });

  it("holds the start button until the page has hydrated, so no click is lost", async () => {
    const container = document.body.appendChild(document.createElement("div"));
    container.innerHTML = renderToString(<StartReplay />);
    const button = () => within(container).getByRole("button", { name: /replay|Loading/ });
    expect(button().textContent).toBe(" Loading…");
    expect((button() as HTMLButtonElement).disabled).toBe(true);
    let root: ReturnType<typeof hydrateRoot> | undefined;
    await act(async () => {
      root = hydrateRoot(container, <StartReplay />);
    });
    expect(button().textContent).toBe(" Start the replay");
    expect((button() as HTMLButtonElement).disabled).toBe(false);
    act(() => root!.unmount());
    container.remove();
  });

  it("reads Starting… while the replay starts, and Start the replay again once it has gone to it", async () => {
    // The start page stays mounted while hidden, so coming back for a new replay finds whatever it
    // showed last.
    const { fetch, answer } = pendingFetch();
    render(<StartReplay />);
    fireEvent.click(startButton());
    expect(startButton().textContent).toBe(" Starting…");
    expect(startButton().disabled).toBe(true);
    await act(async () => answer(201, { run_id: "0123456789abcdef" }));
    expect(fetch).toHaveBeenCalledOnce();
    expect(push).toHaveBeenCalledWith("/runs/0123456789abcdef?as=sam");
    expect(startButton().textContent).toBe(" Start the replay");
    expect(startButton().disabled).toBe(false);
  });

  it("says why a replay couldn't start, and lets the viewer try again", async () => {
    const { answer } = pendingFetch();
    render(<StartReplay />);
    fireEvent.click(startButton());
    await act(async () => answer(429, { error: "Too many replays started from here" }));
    expect(screen.getByRole("alert").textContent).toContain("Too many replays started from here");
    expect(push).not.toHaveBeenCalled();
    expect(startButton().textContent).toBe(" Start the replay");
    expect(startButton().disabled).toBe(false);
  });
});
