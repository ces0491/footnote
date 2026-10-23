import { describe, expect, it, vi } from "vitest";

// server-only throws when imported outside a React Server Component build.
vi.mock("server-only", () => ({}));

import { jsonBody, MAX_BODY_BYTES } from "./body";

const post = (body: BodyInit) => new Request("http://localhost/api/runs", { method: "POST", body, headers: { "content-type": "application/json" } });

/** A request whose content-length says one thing, whatever its body holds. */
function claiming(length: number, body: string): Request {
  const request = post(body);
  return { headers: new Headers({ "content-length": String(length) }), body: request.body } as unknown as Request;
}

async function status(request: Request): Promise<number | null> {
  const read = await jsonBody(request);
  return "response" in read ? read.response.status : null;
}

describe("jsonBody", () => {
  it("reads a JSON body", async () => {
    expect(await jsonBody(post('{"start_minute": 23, "speed": 2}'))).toEqual({ value: { start_minute: 23, speed: 2 } });
  });

  it("gives null for a body that isn't JSON, or for none", async () => {
    expect(await jsonBody(post("start_minute=23"))).toEqual({ value: null });
    expect(await jsonBody(new Request("http://localhost/api/runs", { method: "POST" }))).toEqual({ value: null });
  });

  it("refuses a body over the limit from its content-length, before reading it", async () => {
    expect(await status(claiming(MAX_BODY_BYTES + 1, "{}"))).toBe(413);
  });

  it("refuses a body over the limit however long it claims to be", async () => {
    const big = JSON.stringify({ text: "x".repeat(MAX_BODY_BYTES) });
    expect(await status(post(big))).toBe(413);
    expect(await status(claiming(10, big))).toBe(413);
  });

  it("reads a body right up to the limit", async () => {
    const body = JSON.stringify({ text: "x".repeat(MAX_BODY_BYTES - 20) });
    expect(body.length).toBeLessThanOrEqual(MAX_BODY_BYTES);
    expect(await status(post(body))).toBeNull();
  });
});
