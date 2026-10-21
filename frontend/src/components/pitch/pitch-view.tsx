"use client";

import { useCallback, useMemo } from "react";

import { useTracking } from "@/hooks/use-tracking";
import type { Club, MatchMeta, RunDescriptor, TrackingLayout } from "@/lib/live/contract";
import { langAttribute } from "@/lib/live/language";
import { type Shown, waitText } from "@/lib/live/playback";
import type { Mode } from "@/lib/live/profiles";
import { moment } from "@/lib/live/timeline";
import { cn } from "@/lib/utils";

import { PitchCanvas, type PitchPlayer } from "./pitch-canvas";

/** A graphic on the pitch, as the reference renderer draws the overlay contract (docs/overlay.md). */
function Graphic({ shown, mode, calm, clubs }: { shown: Shown; mode: Mode; calm: boolean; clubs: [Club, Club] }) {
  const { insight } = shown;
  const animate = !calm && insight.motion === "animated";
  const line = mode === "analyst" ? insight.card.analyst : insight.card.casual;
  const wording = langAttribute(shown.lang);
  if (insight.placement === "full_card") {
    return (
      <div
        lang={wording}
        className={cn(
          "absolute inset-x-6 top-1/2 -translate-y-1/2 rounded-xl bg-zinc-950/90 p-5 text-zinc-50 shadow-lg ring-1 ring-white/10",
          animate && "animate-in fade-in duration-500 motion-reduce:animate-none",
        )}
      >
        <div className="text-lg font-semibold">{insight.card.headline}</div>
        <p className="mt-1 text-sm text-zinc-300">{line}</p>
      </div>
    );
  }
  const accent = insight.kind === "correction" ? "#f59e0b" : insight.kind === "rule_call" ? "#38bdf8" : clubs[0].colours[0];
  return (
    <div
      lang={wording}
      className={cn(
        "absolute inset-x-3 bottom-3 overflow-hidden rounded-lg bg-zinc-950/90 text-zinc-50 shadow-lg ring-1 ring-white/10 sm:inset-x-6 sm:bottom-5",
        animate && "animate-in slide-in-from-bottom-4 fade-in duration-500 motion-reduce:animate-none",
      )}
    >
      <div className="flex">
        <span aria-hidden className="w-1.5 shrink-0" style={{ background: accent }} />
        <div className="min-w-0 px-3 py-2">
          <div className="truncate font-semibold">{insight.card.headline}</div>
          {line && <p className="line-clamp-2 text-xs text-zinc-300 sm:text-sm">{line}</p>}
        </div>
      </div>
    </div>
  );
}

/**
 * The match as the viewer's video would show it, drawn from the tracking at their playback, with the
 * graphics that are on screen at that moment. `position` is read on every animation frame.
 */
export function PitchView({
  runId,
  run,
  match,
  layout,
  position,
  graphics,
  mode,
  calm,
  focus,
  waiting,
  caption,
}: {
  runId: string;
  run: RunDescriptor;
  match: MatchMeta;
  layout: TrackingLayout;
  position: () => { at: number; live: number };
  graphics: Shown[];
  mode: Mode;
  calm: boolean;
  focus: string | null;
  waiting: number; // wall seconds until the stream reaches the replay's start
  caption: string;
}) {
  const frameAt = useTracking(runId, run, layout, position);
  const current = useCallback(() => moment(position().at, run.timeline), [position, run.timeline]);
  const clubs = useMemo<[Club, Club]>(() => [match.home, match.away], [match.home, match.away]);
  const players = useMemo(() => {
    const out = new Map<string, PitchPlayer>();
    for (const lineup of match.lineups) {
      const side = lineup.club_id === match.home.id ? 0 : 1;
      for (const p of [...lineup.starters, ...lineup.bench]) out.set(p.player_id, { shirt: p.shirt, side });
    }
    return out;
  }, [match]);
  const breakNow = current() === null;

  return (
    <figure className="relative">
      <PitchCanvas
        layout={layout}
        frameAt={frameAt}
        current={current}
        players={players}
        clubs={clubs}
        focus={focus}
        calm={calm}
        label={caption}
      />
      {waiting > 0 && (
        <div className="absolute inset-0 grid place-items-center rounded-xl bg-black/50 p-6 text-center text-sm text-white">
          The stream reaches the replay&apos;s start in {waitText(waiting)}.
        </div>
      )}
      {breakNow && waiting === 0 && (
        <div className="absolute inset-0 grid place-items-center rounded-xl bg-black/40 text-lg font-semibold text-white">
          Half-time
        </div>
      )}
      {/* The panel beside the pitch carries every graphic's text, for screen readers too (P8). */}
      <div aria-hidden>
        {graphics.map((g) => (
          <Graphic key={g.insight.insight_id} shown={g} mode={mode} calm={calm} clubs={clubs} />
        ))}
      </div>
      <figcaption className="sr-only">{caption}</figcaption>
    </figure>
  );
}
