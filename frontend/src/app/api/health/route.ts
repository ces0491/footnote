// Liveness and readiness for Container Apps. Independent of Postgres and the replayer on purpose:
// a dependency outage shouldn't get the web app restarted.
export function GET() {
  return Response.json({ status: "ok" });
}
