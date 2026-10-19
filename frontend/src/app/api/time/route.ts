import { connection } from "next/server";

// The server's clock, so a browser can place replay time and measure latency against it.
export async function GET() {
  await connection();
  return Response.json({ now: Date.now() }, { headers: { "cache-control": "no-store" } });
}
