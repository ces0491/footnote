import { notFound } from "next/navigation";
import { Suspense } from "react";

import { LiveRun } from "@/components/live/live-run";
import { runIdPattern } from "@/lib/live/contract";

async function Run({ params, searchParams }: PageProps<"/runs/[runId]">) {
  const { runId } = await params;
  const { as } = await searchParams;
  if (!runIdPattern.test(runId)) notFound();
  // Keyed so another run's page starts from a fresh state rather than this one's. `as` names the
  // ready-made viewer to start as (lib/live/profiles.ts).
  return <LiveRun key={runId} runId={runId} initialProfile={typeof as === "string" ? as : null} />;
}

export default function RunPage(props: PageProps<"/runs/[runId]">) {
  return (
    // Full width: the run's page sets its own columns under a header that spans the screen.
    <main className="w-full flex-1">
      {/* Hidden: on screen, the scoreboard says which match this is. */}
      <h1 className="sr-only">Replay of the showcase match</h1>
      <Suspense>
        <Run {...props} />
      </Suspense>
    </main>
  );
}
