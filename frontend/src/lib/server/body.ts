import "server-only";

// The largest JSON body a route reads. A producer's edit is the longest request the page sends: a
// headline and a few sentences of wording.
export const MAX_BODY_BYTES = 16 * 1024;

export type JsonBody = { value: unknown } | { response: Response };

const tooLarge = (): JsonBody => ({
  response: Response.json({ error: "The request is too large", problems: [] }, { status: 413 }),
});

/**
 * The request's JSON body, read up to MAX_BODY_BYTES; past that, a 413 response to return. The
 * content-length is checked when the client sends one, and what is read is counted either way, so a
 * body without a length, or with a false one, stops at the limit too. A body that isn't JSON gives
 * null, for the route's schema to refuse.
 */
export async function jsonBody(request: Request): Promise<JsonBody> {
  if (Number(request.headers.get("content-length")) > MAX_BODY_BYTES) return tooLarge();
  const reader = request.body?.getReader();
  if (!reader) return { value: null };
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_BODY_BYTES) {
      await reader.cancel();
      return tooLarge();
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(size);
  let at = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, at);
    at += chunk.byteLength;
  }
  try {
    return { value: JSON.parse(new TextDecoder().decode(bytes)) };
  } catch {
    return { value: null };
  }
}
