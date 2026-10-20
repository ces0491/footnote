"use client";

import { ArrowLeft, Square } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { type Connection, type Latency, useLiveRun } from "@/hooks/use-live-run";
import { useNow } from "@/hooks/use-now";
import type { Clock, RunDescriptor, RunEndReason, StateView } from "@/lib/live/contract";
import { roster } from "@/lib/live/describe";
import { clockLabel, liveReplaySecond, moment } from "@/lib/live/timeline";

import { MatchStatePanel } from "./match-state";
import { Scoreboard } from "./scoreboard";
import { Shortlist } from "./shortlist";
import { StatsPanel } from "./stats-panel";
import { Ticker } from "./ticker";

const ENDED: Record<RunEndReason, string> = {
  finished: "The replay reached full time.",
  stopped: "The replay was stopped.",
  expired: "The replay reached its time limit.",
  evicted: "The replay was stopped to make room for a newer one.",
  failed: "The replay failed. Start another.",
};

/** What the clock shows: ticking with the replay while it runs, the last event's clock once it ends. */
function displayClock(view: StateView, run: RunDescriptor, serverNow: number, ended: boolean): string {
  if (view.phase === "half_time") return "HT";
  if (view.phase === "full_time") return "FT";
  if (ended || view.phase === "pre_match") return view.clock ? lastClock(view.clock) : "0:00";
  const m = moment(liveReplaySecond(run, serverNow), run.timeline);
  return m ? clockLabel(m) : "HT";
}

function lastClock(clock: Clock): string {
  return clockLabel({ period: clock.period === 1 ? 1 : 2, t: clock.t });
}

const CONNECTION: Record<Connection, { label: string; dot: string }> = {
  connecting: { label: "Connecting…", dot: "bg-amber-500" },
  connected: { label: "Live", dot: "bg-emerald-500" },
  reconnecting: { label: "Reconnecting…", dot: "bg-amber-500" },
  polling: { label: "Refreshing every few seconds", dot: "bg-amber-500" },
  closed: { label: "Closed", dot: "bg-zinc-400" },
};

function ConnectionBadge({ connection, latency }: { connection: Connection; latency: Latency | null }) {
  const { label, dot } = CONNECTION[connection];
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <Badge variant="outline" className="gap-1.5">
        <span aria-hidden className={`size-2 rounded-full ${dot}`} />
        {label}
      </Badge>
      {latency && (
        <span className="text-muted-foreground" title="From the replayer publishing an event to this browser receiving it">
          Publish to browser: p50 {Math.round(latency.p50)} ms · p95 {Math.round(latency.p95)} ms ({latency.samples} events)
        </span>
      )}
    </div>
  );
}

export function LiveRun({ runId }: { runId: string }) {
  const live = useLiveRun(runId);
  const [stopping, setStopping] = useState(false);
  const ended = live.ended !== null;
  const now = useNow(250, !ended);
  const r = useMemo(() => (live.snapshot ? roster(live.snapshot.match) : null), [live.snapshot]);

  async function stop() {
    setStopping(true);
    await fetch(`/api/runs/${runId}`, { method: "DELETE" }).catch(() => undefined);
    setStopping(false);
  }

  const header = (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <Button variant="ghost" size="sm" asChild>
        <Link href="/">
          <ArrowLeft /> New replay
        </Link>
      </Button>
      <div className="flex flex-wrap items-center gap-3">
        <ConnectionBadge connection={live.connection} latency={live.latency} />
        {!ended && (
          <Button variant="outline" size="sm" onClick={stop} disabled={stopping}>
            <Square /> Stop
          </Button>
        )}
      </div>
    </div>
  );

  if (live.error) {
    return (
      <div className="space-y-4">
        {header}
        <Alert variant="destructive">
          <AlertTitle>Couldn&apos;t follow this replay</AlertTitle>
          <AlertDescription>{live.error}</AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!live.snapshot || !live.view || !r) {
    return (
      <div className="space-y-4">
        {header}
        <Skeleton className="h-28 w-full rounded-xl" />
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-96" />
          <Skeleton className="h-96" />
        </div>
      </div>
    );
  }

  const { match, run } = live.snapshot;
  const view = live.view;
  return (
    <div className="space-y-4">
      {header}
      {live.trouble && (
        <Alert>
          <AlertTitle>Connection trouble</AlertTitle>
          <AlertDescription>{live.trouble} What is shown here is the latest the page has.</AlertDescription>
        </Alert>
      )}
      <Scoreboard
        home={match.home}
        away={match.away}
        score={view.score}
        phase={view.phase}
        clock={displayClock(view, run, now + live.offset, ended)}
      />
      {live.ended && (
        <Alert>
          <AlertTitle>Replay over</AlertTitle>
          <AlertDescription>{ENDED[live.ended]}</AlertDescription>
        </Alert>
      )}
      <MatchStatePanel home={match.home} away={match.away} state={view.match_state} timeline={view.state_timeline ?? []} />
      <Shortlist runId={runId} insights={live.insights} clock={view.clock} roster={r} />
      <div className="grid gap-4 md:grid-cols-2">
        <StatsPanel home={match.home} away={match.away} stats={view.teams} />
        <Ticker events={view.key_events} tags={view.tags ?? []} roster={r} />
      </div>
      <p className="text-xs text-muted-foreground">
        {match.competition} {match.season} · {match.venue} · Referee {match.referee.name} · Replay from {run.start_minute}&apos; at {run.speed}×
      </p>
    </div>
  );
}
