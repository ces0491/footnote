import { notFound } from "next/navigation";
import { Suspense } from "react";

import { LiveRun } from "@/components/live/live-run";
import { runIdPattern } from "@/lib/live/contract";

async function Run({ params }: { params: PageProps<"/runs/[runId]">["params"] }) {
  const { runId } = await params;
  if (!runIdPattern.test(runId)) notFound();
  // Keyed so another run's page starts from a fresh state rather than this one's.
  return <LiveRun key={runId} runId={runId} />;
}

export default function RunPage({ params }: PageProps<"/runs/[runId]">) {
  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6 sm:py-10">
      <Suspense>
        <Run params={params} />
      </Suspense>
    </main>
  );
}
