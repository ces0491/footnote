// @vitest-environment jsdom
import { act, cleanup, render, screen, within } from "@testing-library/react";
import { hydrateRoot } from "react-dom/client";
import { renderToString } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StartReplay } from "./start-replay";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

afterEach(cleanup);

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
});
