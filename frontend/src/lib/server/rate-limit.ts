import "server-only";

/**
 * A fixed-window limit on requests per client address, held in this replica's memory (the web app
 * runs one replica).
 */
export class Limit {
  private readonly windows = new Map<string, { start: number; count: number }>();

  constructor(
    private readonly windowMs: number,
    private readonly max: number,
  ) {}

  /** Counts a request from `clientAddress`; false once its window has had `max` of them. */
  allow(clientAddress: string, now = Date.now()): boolean {
    for (const [key, window] of this.windows) {
      if (now - window.start > this.windowMs) this.windows.delete(key);
    }
    const window = this.windows.get(clientAddress);
    if (!window) {
      this.windows.set(clientAddress, { start: now, count: 1 });
      return true;
    }
    if (window.count >= this.max) return false;
    window.count += 1;
    return true;
  }

  /** Whole seconds until `clientAddress`'s window ends, for a Retry-After header. */
  retryAfter(clientAddress: string, now = Date.now()): number {
    const window = this.windows.get(clientAddress);
    return window ? Math.max(1, Math.ceil((window.start + this.windowMs - now) / 1000)) : 1;
  }
}

// Replay starts. A viewer's own restarts don't fill the replayer's run slots, since each replaces
// their last run (lib/live/viewer.ts); this slows a script that starts runs regardless.
export const starts = new Limit(5 * 60_000, 8);

// Web PubSub client URLs. A page asks for one when it connects, and again every 30 seconds while it
// follows by polling; this keeps a script from collecting URLs to hold connections open with. A page
// turned away follows by polling.
export const negotiations = new Limit(5 * 60_000, 60);

// Container Apps' ingress appends the caller's address to X-Forwarded-For, after anything the caller
// sent in that header itself, so only the last entry can be trusted.
export function clientAddress(headers: Headers): string {
  return headers.get("x-forwarded-for")?.split(",").at(-1)?.trim() || "unknown";
}
