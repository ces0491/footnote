"use client";

import { ArrowLeft, Square } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";

import { PitchView } from "@/components/pitch/pitch-view";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { type Connection, type Latency, useLiveRun } from "@/hooks/use-live-run";
import { useMediaQuery } from "@/hooks/use-media-query";
import { useNow } from "@/hooks/use-now";
import { usePlaybackView } from "@/hooks/use-playback-view";
import type { Clock, DeskRefusal, InsightMessage, ProducerMode, RunEndReason, RunSnapshot, StateView } from "@/lib/live/contract";
import { roster } from "@/lib/live/describe";
import { forMode } from "@/lib/live/fan";
import { airing, DELAYS, delayText, insightsAt, onScreenAt, playbackOf, reached } from "@/lib/live/playback";
import {
  profile as profileOf,
  type Profile,
  resetSettings,
  savedSettingsText,
  saveSettings,
  type Settings,
  settingsFrom,
  startedHere,
  subscribeSettings,
} from "@/lib/live/profiles";
import { clockLabel, moment } from "@/lib/live/timeline";
import { viewerId } from "@/lib/live/viewer";
import { cn } from "@/lib/utils";

import { FanPanel } from "./fan-panel";
import { MatchStatePanel } from "./match-state";
import { ProducerConsole } from "./producer-console";
import { Scoreboard } from "./scoreboard";
import { StatsPanel } from "./stats-panel";
import { Ticker } from "./ticker";
import { ProfileSwitch, SettingsDialog } from "./viewer-bar";

const ENDED: Record<RunEndReason, string> = {
  finished: "The replay reached full time.",
  stopped: "The replay was stopped.",
  expired: "The replay reached its time limit.",
  evicted: "The replay was stopped to make room for a newer one.",
  failed: "The replay failed. Start another.",
};

// The producer's preview of the world feed runs as far behind live as the shortest fan stream, the
// least lead the pitch view needs to fetch the tracking.
const PREVIEW_DELAY = DELAYS[0];

const never = () => () => {};

function lastClock(clock: Clock): string {
  return clockLabel({ period: clock.period === 1 ? 1 : 2, t: clock.t });
}

/** What the clock shows at replay second `at`: ticking with playback, the last event's once the run is over. */
function clockAt(view: StateView, timeline: { first_half_end: number; half_time: number }, at: number, ended: boolean): string {
  if (view.phase === "half_time") return "HT";
  if (view.phase === "full_time") return "FT";
  if (ended || view.phase === "pre_match") return view.clock ? lastClock(view.clock) : "0:00";
  const m = moment(at, timeline);
  return m ? clockLabel(m) : "HT";
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

export function LiveRun({ runId, initialProfile }: { runId: string; initialProfile: string | null }) {
  const live = useLiveRun(runId);
  const router = useRouter();
  const pathname = usePathname();
  const [current, setCurrent] = useState<Profile>(() => profileOf(initialProfile));
  // A mode the producer switched to, until the next snapshot reports the run's own.
  const [switched, setSwitched] = useState<{ mode: ProducerMode; snapshot: RunSnapshot | null } | null>(null);
  const [stopping, setStopping] = useState(false);
  const ended = live.ended !== null;
  const now = useNow(250, true);
  // The match stays the same object across refetches (useLiveRun keeps it), so the roster does too.
  const shownMatch = live.snapshot?.match;
  const r = useMemo(() => (shownMatch ? roster(shownMatch) : null), [shownMatch]);
  // A phone shows the panel only: the pitch view isn't drawn or fed there at all.
  const wide = useMediaQuery("(min-width: 768px)");

  // What this browser keeps: its ID, whether it started this replay, and each profile's settings.
  const viewer = useSyncExternalStore(never, viewerId, () => "");
  const canProduce = useSyncExternalStore(never, () => startedHere(runId), () => false);
  const saved = useSyncExternalStore(subscribeSettings, savedSettingsText, () => "");
  const settings = useMemo(() => settingsFrom(saved, current), [saved, current]);
  const mode = switched && switched.snapshot === live.snapshot ? switched.mode : (live.snapshot?.producer ?? "auto");

  const pick = useCallback(
    (id: Profile["id"]) => {
      setCurrent(profileOf(id));
      router.replace(`${pathname}?as=${id}`, { scroll: false });
    },
    [router, pathname],
  );
  const change = useCallback((next: Settings) => saveSettings(current, next), [current]);

  const producer = current.role === "producer";
  const delay = producer ? PREVIEW_DELAY : settings.delay;
  const run = live.snapshot?.run ?? null;
  const offset = live.offset;
  const state = live.state;
  const { base, events, view: liveView } = state;
  // Once the run has ended, live stays at its last event; a delayed stream plays on up to it.
  const liveEnd = ended ? (events.at(-1)?.replay ?? run?.start_replay ?? Infinity) : Infinity;
  const position = useCallback(() => {
    const p = run ? playbackOf(run, Date.now() + offset, delay, liveEnd) : { at: 0, live: 0, waiting: 0 };
    return { at: p.at, live: p.live };
  }, [run, offset, delay, liveEnd]);

  const pb = run ? playbackOf(run, now + offset, producer ? 0 : delay, liveEnd) : null;
  const count = pb ? reached(events, pb.at) : 0;
  // Whether this viewer's stream has reached the end of a run that has ended: until then, nothing on
  // the page says it has.
  const caughtUp = !ended || count >= events.length;
  const atPlayback = usePlaybackView(base, events, liveView, count);
  const shown = run && pb ? insightsAt(state, run, pb.at) : [];
  const preview = run ? playbackOf(run, now + offset, PREVIEW_DELAY, liveEnd) : null;

  // Calm mode reaches everything on the page, dialogs included, which render outside this component.
  const calm = !producer && settings.calm;
  useEffect(() => {
    const root = document.documentElement;
    if (calm) root.dataset.calm = "";
    else delete root.dataset.calm;
    return () => {
      delete root.dataset.calm;
    };
  }, [calm]);

  async function stop() {
    setStopping(true);
    await fetch(`/api/runs/${runId}`, {
      method: "DELETE",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ viewer }),
    }).catch(() => undefined);
    setStopping(false);
  }

  async function switchMode(next: ProducerMode): Promise<string | null> {
    const response = await fetch(`/api/runs/${runId}/producer`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ viewer, mode: next }),
    }).catch(() => null);
    if (!response) return "The producer's desk isn't answering; try again";
    const body = (await response.json()) as { producer: ProducerMode } | DeskRefusal;
    if ("error" in body) return body.error;
    setSwitched({ mode: body.producer, snapshot: live.snapshot });
    return null;
  }

  const header = (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/">
            <ArrowLeft /> New replay
          </Link>
        </Button>
        <ProfileSwitch current={current} onPick={pick} />
        {!producer && live.snapshot && (
          <SettingsDialog
            profile={current}
            settings={settings}
            match={live.snapshot.match}
            onChange={change}
            onReset={() => resetSettings(current)}
          />
        )}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        {/* A delayed stream is still playing after the run ends; the badge says so until it has finished. */}
        <ConnectionBadge connection={producer || caughtUp ? live.connection : "connected"} latency={live.latency} />
        {/* Only the browser that started the replay stops it, as only it produces it. */}
        {canProduce && !ended && (
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

  if (!live.snapshot || !live.view || !atPlayback || !r || !run || !pb || !preview) {
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

  const { match, tracking } = live.snapshot;
  const footer = (
    <p className="text-xs text-muted-foreground">
      {match.competition} {match.season} · {match.venue} · Referee {match.referee.name} · Replay from {run.start_minute}&apos; at {run.speed}×
    </p>
  );
  const notices = (
    <>
      {live.trouble && (
        <Alert>
          <AlertTitle>Connection trouble</AlertTitle>
          <AlertDescription>{live.trouble} What is shown here is the latest the page has.</AlertDescription>
        </Alert>
      )}
      {/* Said politely, and to a fan only once their stream has reached the end. */}
      {live.ended && (producer || caughtUp) && (
        <Alert role="status">
          <AlertTitle>Replay over</AlertTitle>
          <AlertDescription>{ENDED[live.ended]}</AlertDescription>
        </Alert>
      )}
    </>
  );

  if (producer) {
    const view = live.view;
    const onAir = onScreenAt(airing(insightsAt(state, run, preview.at)), preview.at, run.speed);
    return (
      <div className="space-y-4">
        {header}
        {notices}
        <Scoreboard home={match.home} away={match.away} score={view.score} phase={view.phase} clock={clockAt(view, run.timeline, pb.live, ended)} />
        <MatchStatePanel home={match.home} away={match.away} state={view.match_state} timeline={view.state_timeline ?? []} />
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_28rem]">
          <div className="space-y-2">
            {tracking && (
              <PitchView
                runId={runId}
                run={run}
                match={match}
                layout={tracking}
                position={position}
                graphics={onAir}
                mode="casual"
                calm={false}
                focus={null}
                waiting={preview.waiting / run.speed}
                caption={`The world feed's preview, ${PREVIEW_DELAY} seconds behind live, with the graphics on air`}
              />
            )}
            <p className="text-xs text-muted-foreground">
              Preview of the world feed, {PREVIEW_DELAY} seconds behind live: our own render of the tracking, with the
              graphics on air.{" "}
              {onAir.length > 0 ? `On air: ${onAir.map((s) => s.insight.card.headline).join(", ")}.` : "Nothing on air."}
            </p>
          </div>
          <ProducerConsole
            runId={runId}
            insights={live.insights}
            clock={view.clock}
            roster={r}
            viewer={viewer}
            canProduce={canProduce && !ended}
            mode={mode}
            onMode={switchMode}
            onChange={(message: InsightMessage) => live.receive(message)}
          />
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <StatsPanel home={match.home} away={match.away} stats={view.teams} />
          <Ticker events={view.key_events} tags={view.tags ?? []} roster={r} />
        </div>
        {footer}
      </div>
    );
  }

  const cards = forMode(airing(shown), settings.mode);
  const graphics = settings.graphics ? onScreenAt(cards, pb.at, run.speed) : [];
  const focus = settings.player ? (r.player(settings.player) ?? null) : null;
  const analyst = settings.mode === "analyst";
  const clock = clockAt(atPlayback, run.timeline, pb.at, ended && caughtUp);
  const pitch = Boolean(tracking) && wide && settings.pitch;
  const behind = delayText(settings.delay, run.speed);
  return (
    <div className="space-y-4">
      {header}
      {notices}
      <Scoreboard home={match.home} away={match.away} score={atPlayback.score} phase={atPlayback.phase} clock={clock} />
      <p className="text-sm text-muted-foreground">
        {pb.waiting > 0
          ? `Your stream is ${behind}: it reaches the replay's start in ${Math.ceil(pb.waiting / run.speed)} seconds.`
          : `Your stream: ${behind}. Nothing reaches this page before your stream shows it.`}
      </p>
      <div className={cn("grid gap-4", pitch && "lg:grid-cols-[minmax(0,1fr)_24rem]")}>
        {pitch && tracking && (
          <div>
            <PitchView
              runId={runId}
              run={run}
              match={match}
              layout={tracking}
              position={position}
              graphics={graphics}
              mode={settings.mode}
              calm={settings.calm}
              focus={settings.player}
              waiting={pb.waiting / run.speed}
              caption={`The match at ${clock} on your stream, drawn from the tracking`}
            />
          </div>
        )}
        <FanPanel
          runId={runId}
          match={match}
          layout={tracking}
          view={atPlayback}
          cards={cards}
          settings={settings}
          roster={r}
          focus={focus}
        />
      </div>
      {analyst && (
        <MatchStatePanel home={match.home} away={match.away} state={atPlayback.match_state} timeline={atPlayback.state_timeline ?? []} />
      )}
      <div className="grid gap-4 md:grid-cols-2">
        {analyst && <StatsPanel home={match.home} away={match.away} stats={atPlayback.teams} />}
        <Ticker events={atPlayback.key_events} tags={atPlayback.tags ?? []} roster={r} />
      </div>
      {footer}
    </div>
  );
}
