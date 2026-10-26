"use client";

import { Plus, Square, Timer } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";

import { Wordmark } from "@/components/brand";
import { PitchView } from "@/components/pitch/pitch-view";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { type Connection, type Latency, useLiveRun } from "@/hooks/use-live-run";
import { useMediaQuery } from "@/hooks/use-media-query";
import { useNow } from "@/hooks/use-now";
import { usePlaybackView } from "@/hooks/use-playback-view";
import { catchUpOf, keyMoments } from "@/lib/live/catch-up";
import type { Clock, DeskRefusal, InsightMessage, ProducerMode, RunEndReason, RunSnapshot, StateView } from "@/lib/live/contract";
import { roster } from "@/lib/live/describe";
import { forMode } from "@/lib/live/fan";
import { localized } from "@/lib/live/language";
import { airing, DELAYS, delayText, insightsAt, onScreenAt, playbackOf, reached, waitText } from "@/lib/live/playback";
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

import { DescribedFeed } from "./described-feed";
import { FanPanel } from "./fan-panel";
import { MatchStatePanel } from "./match-state";
import { ProducerConsole } from "./producer-console";
import { Scoreboard } from "./scoreboard";
import { StatsPanel } from "./stats-panel";
import { Ticker } from "./ticker";
import { ProfileSwitch, SettingsSheet } from "./viewer-bar";

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

// Live is the broadcast's red; anything short of a live connection is grey.
const CONNECTION: Record<Connection, { label: string; dot: string }> = {
  connecting: { label: "Connecting…", dot: "animate-pulse bg-muted-foreground" },
  connected: { label: "Live", dot: "bg-tally" },
  reconnecting: { label: "Reconnecting…", dot: "animate-pulse bg-muted-foreground" },
  polling: { label: "Refreshing every few seconds", dot: "bg-muted-foreground" },
  closed: { label: "Closed", dot: "bg-edge" },
};

function ConnectionBadge({ connection, latency }: { connection: Connection; latency: Latency | null }) {
  const { label, dot } = CONNECTION[connection];
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="inline-flex items-center gap-2 font-medium">
        <span aria-hidden className={cn("size-2 rounded-full", dot)} />
        {label}
      </span>
      {/* On a phone the latency line would take much of the screen, so it shows from the sm breakpoint up. */}
      {latency && (
        <span
          className="hidden text-xs text-muted-foreground sm:inline"
          title="From the replayer publishing an event to this browser receiving it. After a jump, from 10 s in: the processor first takes in the match so far."
        >
          Publish to browser: p50 {Math.round(latency.p50)} ms, p95 {Math.round(latency.p95)} ms ({latency.samples} events)
        </span>
      )}
    </div>
  );
}

/** The columns a run's page is laid out in on a wide screen: the match to the left, the viewer's
 * panel to the right. Each block keeps its place in the page's order, which a phone shows top to
 * bottom: what plays (the pitch, or the described feed), the panel, then the figures. */
function Columns({ top, side, rest, wide }: { top: ReactNode; side: ReactNode; rest: ReactNode; wide: string }) {
  return (
    <div className={cn("grid gap-5 lg:items-start", wide, top && "lg:grid-rows-[auto_1fr]")}>
      {top && <div className="min-w-0 space-y-5 lg:col-start-1 lg:row-start-1">{top}</div>}
      <div className="min-w-0 lg:col-start-2 lg:row-span-2 lg:row-start-1">{side}</div>
      <div className={cn("min-w-0 space-y-5 lg:col-start-1", top ? "lg:row-start-2" : "lg:row-start-1")}>{rest}</div>
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
  // A fan joining mid-match starts on the catch-up.
  const [catchUpOpen, setCatchUpOpen] = useState(true);
  const ended = live.ended !== null;
  const now = useNow(250, true);
  // The match stays the same object across refetches (useLiveRun keeps it), so the roster does too.
  const shownMatch = live.snapshot?.match;
  const r = useMemo(() => (shownMatch ? roster(shownMatch) : null), [shownMatch]);
  // A phone has no pitch view: it isn't drawn or fed there.
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
    <div className="border-b bg-background/90 backdrop-blur md:sticky md:top-0 md:z-30">
      <div className="mx-auto max-w-7xl space-y-2.5 px-4 py-3 sm:px-6">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 sm:gap-4">
            <Wordmark className="text-xl" />
            {/* Icons alone on a phone, where the top row is short of room; the names stay for screen readers. */}
            <Button variant="ghost" size="sm" asChild>
              <Link href="/" aria-label="New replay">
                <Plus /> <span className="hidden sm:inline">New replay</span>
              </Link>
            </Button>
          </div>
          <div className="flex items-center gap-3">
            {/* A delayed stream is still playing after the run ends; the badge says so until it has finished. */}
            {!live.error && <ConnectionBadge connection={producer || caughtUp ? live.connection : "connected"} latency={live.latency} />}
            {/* Only the browser that started the replay stops it, as only it produces it. */}
            {canProduce && !ended && (
              <Button variant="outline" size="sm" onClick={stop} disabled={stopping} aria-label="Stop">
                <Square /> <span className="hidden sm:inline">Stop</span>
              </Button>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span aria-hidden className="hidden shrink-0 text-sm text-muted-foreground sm:inline">
            Watch as
          </span>
          <div className="min-w-0 flex-1">
            <ProfileSwitch current={current} onPick={pick} />
          </div>
          {!producer && live.snapshot && (
            <SettingsSheet
              profile={current}
              settings={settings}
              match={live.snapshot.match}
              onChange={change}
              onReset={() => resetSettings(current)}
            />
          )}
        </div>
      </div>
    </div>
  );

  const body = (children: ReactNode) => (
    <>
      {header}
      <div className="mx-auto w-full max-w-7xl space-y-5 px-4 py-5 sm:px-6 sm:py-6">{children}</div>
    </>
  );

  if (live.error) {
    return body(
      <Alert variant="destructive">
        <AlertTitle>Couldn&apos;t follow this replay</AlertTitle>
        <AlertDescription>
          <p>{live.error}</p>
          <Button size="sm" asChild>
            <Link href="/">Start a new replay</Link>
          </Button>
        </AlertDescription>
      </Alert>,
    );
  }

  if (!live.snapshot || !live.view || !atPlayback || !r || !run || !pb || !preview) {
    return body(
      <>
        <Skeleton className="h-28 w-full rounded-xl" />
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_26rem]">
          <Skeleton className="aspect-111/74 w-full rounded-xl" />
          <Skeleton className="h-96 rounded-xl" />
        </div>
      </>,
    );
  }

  const { match, tracking } = live.snapshot;
  const footer = (
    <footer className="flex flex-wrap gap-x-6 gap-y-1 border-t pt-4 text-xs text-muted-foreground">
      <span>
        {match.competition} {match.season}
      </span>
      <span>{match.venue}</span>
      <span>Referee {match.referee.name}</span>
      <span>
        Replay from {run.start_minute}&apos; at {run.speed}×
      </span>
    </footer>
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
    const onAir = onScreenAt(airing(insightsAt(state, run, preview.at)), preview.at, run, PREVIEW_DELAY);
    return body(
      <>
        {notices}
        <Scoreboard home={match.home} away={match.away} score={view.score} phase={view.phase} clock={clockAt(view, run.timeline, pb.live, ended)} />
        <Columns
          wide="lg:grid-cols-[minmax(0,1fr)_26rem] xl:grid-cols-[minmax(0,1fr)_30rem]"
          top={
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
                <h2 className="text-xl font-bold tracking-tight font-stretch-75%">World feed</h2>
                <p className="flex items-center gap-2 text-sm font-medium">
                  <span aria-hidden className={cn("size-2.5 rounded-full", onAir.length > 0 ? "bg-tally" : "bg-edge")} />
                  {onAir.length > 0 ? `On air: ${onAir.map((s) => s.insight.card.headline).join(", ")}.` : "Nothing on air."}
                </p>
              </div>
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
                  caption={`Preview of the world feed, ${delayText(PREVIEW_DELAY, run.speed)}: our own render of the tracking, with the graphics on air`}
                />
              )}
              {/* The pitch's own label says this to a screen reader. */}
              <p aria-hidden className="text-xs text-muted-foreground">
                Preview of the world feed, {delayText(PREVIEW_DELAY, run.speed)}: our own render of the tracking, with the graphics on air.
              </p>
            </div>
          }
          side={
            <ProducerConsole
              runId={runId}
              insights={live.insights}
              clock={view.clock}
              roster={r}
              viewer={viewer}
              canProduce={canProduce && !ended}
              ended={ended}
              mode={mode}
              onMode={switchMode}
              onChange={(message: InsightMessage) => live.receive(message)}
            />
          }
          rest={
            <>
              <MatchStatePanel home={match.home} away={match.away} state={view.match_state} timeline={view.state_timeline ?? []} />
              <div className="grid gap-5 xl:grid-cols-2">
                <StatsPanel home={match.home} away={match.away} stats={view.teams} />
                <Ticker events={view.key_events} tags={view.tags ?? []} roster={r} />
              </div>
            </>
          }
        />
        {footer}
      </>,
    );
  }

  const cards = localized(forMode(airing(shown), settings.mode), settings.language);
  const graphics = settings.graphics ? onScreenAt(cards, pb.at, run, settings.delay) : [];
  const focus = settings.player ? (r.player(settings.player) ?? null) : null;
  const analyst = settings.mode === "analyst";
  const clock = clockAt(atPlayback, run.timeline, pb.at, ended && caughtUp);
  const pitch = Boolean(tracking) && wide && settings.pitch;
  const behind = delayText(settings.delay, run.speed);
  // The catch-up names the goals and leaves the score to the scoreboard.
  const catchUpCard = catchUpOf(cards);
  const catchUp = catchUpCard && {
    insight: catchUpCard.insight,
    lang: catchUpCard.lang,
    moments: keyMoments(shown, settings.language),
    open: catchUpOpen,
    onOpen: () => setCatchUpOpen(true),
    onClose: () => setCatchUpOpen(false),
  };
  const described = settings.described && base && (
    <DescribedFeed
      match={match}
      roster={r}
      base={base}
      startReplay={run.start_replay}
      events={events}
      reached={count}
      cards={cards}
      detail={settings.detail}
      pace={settings.pace}
      onDetail={(detail) => change({ ...settings, detail })}
      onPace={(pace) => change({ ...settings, pace })}
    />
  );
  return body(
    <>
      {notices}
      <Scoreboard home={match.home} away={match.away} score={atPlayback.score} phase={atPlayback.phase} clock={clock} />
      <p className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-sm text-muted-foreground">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-secondary px-2.5 py-1 font-medium text-foreground">
          <Timer aria-hidden className="size-3.5" />
          Your stream
        </span>
        {pb.waiting > 0
          ? `is ${behind}: it reaches the replay's start in ${waitText(pb.waiting / run.speed)}.`
          : `${behind}. Nothing reaches this page before your stream shows it.`}
      </p>
      <Columns
        wide="lg:grid-cols-[minmax(0,1fr)_24rem] xl:grid-cols-[minmax(0,1fr)_27rem]"
        top={
          (described || (pitch && tracking)) && (
            <>
              {described}
              {pitch && tracking && (
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
              )}
            </>
          )
        }
        side={
          <FanPanel
            key={current.id}
            runId={runId}
            match={match}
            layout={tracking}
            view={atPlayback}
            cards={cards}
            catchUp={catchUp}
            settings={settings}
            roster={r}
            focus={focus}
          />
        }
        rest={
          <>
            {analyst && (
              <MatchStatePanel home={match.home} away={match.away} state={atPlayback.match_state} timeline={atPlayback.state_timeline ?? []} />
            )}
            {analyst && <StatsPanel home={match.home} away={match.away} stats={atPlayback.teams} />}
            <Ticker events={atPlayback.key_events} tags={atPlayback.tags ?? []} roster={r} />
          </>
        }
      />
      {footer}
    </>,
  );
}
