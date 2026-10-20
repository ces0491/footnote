import "server-only";

// A fixed-window limit on replay starts per client address, held in this replica's memory (the web
// app runs one replica). It keeps one visitor from cycling through the replayer's run slots.
const WINDOW_MS = 5 * 60_000;
const MAX_STARTS = 8;

const windows = new Map<string, { start: number; count: number }>();

export function allowStart(clientAddress: string, now = Date.now()): boolean {
  for (const [key, window] of windows) {
    if (now - window.start > WINDOW_MS) windows.delete(key);
  }
  const window = windows.get(clientAddress);
  if (!window) {
    windows.set(clientAddress, { start: now, count: 1 });
    return true;
  }
  if (window.count >= MAX_STARTS) return false;
  window.count += 1;
  return true;
}

// Container Apps' ingress appends the caller's address to X-Forwarded-For, after anything the caller
// sent in that header itself, so only the last entry can be trusted.
export function clientAddress(headers: Headers): string {
  return headers.get("x-forwarded-for")?.split(",").at(-1)?.trim() || "unknown";
}
