"use client";

import { useCallback, useMemo } from "react";

import { clubOf, EDGE, kindOf } from "@/components/live/card-kind";
import { useTracking } from "@/hooks/use-tracking";
import { clubColour, inkOn, NIGHT } from "@/lib/club-colour";
import type { Club, MatchMeta, RunDescriptor, TrackingLayout } from "@/lib/live/contract";
import { langAttribute } from "@/lib/live/language";
import { type Shown, waitText } from "@/lib/live/playback";
import type { Mode } from "@/lib/live/profiles";
import { minuteLabel, moment } from "@/lib/live/timeline";
import { cn } from "@/lib/utils";

import { PitchCanvas, type PitchPlayer } from "./pitch-canvas";

/**
 * A graphic on the pitch, as the reference renderer draws the overlay contract (docs/overlay.md): a
 * lower third led by the minute in the colour of the club it's about (or of its kind, for one that
 * isn't about a club), or a full card over the middle of the pitch.
 */
function Graphic({ shown, mode, calm, match }: { shown: Shown; mode: Mode; calm: boolean; match: MatchMeta }) {
  const { insight } = shown;
  const animate = !calm && insight.motion === "animated";
  const line = mode === "analyst" ? insight.card.analyst : insight.card.casual;
  const wording = langAttribute(shown.lang);
  if (insight.placement === "full_card") {
    return (
      <div
        lang={wording}
        className={cn(
          "absolute inset-x-6 top-1/2 -translate-y-1/2 chamfer bg-night/92 px-6 py-5 text-center shadow-2xl sm:inset-x-[12%]",
          animate && "animate-in duration-500 fade-in zoom-in-95",
        )}
      >
        <div className="text-2xl leading-tight font-bold tracking-tight font-stretch-75% sm:text-3xl">{insight.card.headline}</div>
        <p className="mx-auto mt-2 max-w-prose font-serif text-sm leading-relaxed text-foreground/85 sm:text-base">{line}</p>
      </div>
    );
  }
  const club = clubOf(insight, match.home, match.away);
  const accent = club ? clubColour(club) : EDGE[kindOf(insight).tone];
  const Icon = kindOf(insight).icon;
  return (
    <div
      lang={wording}
      className={cn(
        "absolute inset-x-3 bottom-3 flex chamfer-sm shadow-2xl sm:inset-x-6 sm:bottom-5",
        animate && "animate-in duration-500 fade-in slide-in-from-bottom-4",
      )}
    >
      <div className="flex w-14 shrink-0 flex-col items-center justify-center gap-1 sm:w-16" style={{ background: accent, color: club ? inkOn(accent) : NIGHT }}>
        <Icon aria-hidden className="size-4" />
        {/* Large text (20px bold), which needs 3:1: on a lightened kit colour neither ink reaches 4.5:1. */}
        <span className="text-xl leading-none font-bold figures">{minuteLabel(insight.at.minute ?? 0, insight.at.added_minute ?? null)}</span>
      </div>
      <div className="min-w-0 flex-1 bg-night/92 px-4 py-2.5">
        <div className="truncate text-lg leading-tight font-bold tracking-tight font-stretch-75% sm:text-xl">{insight.card.headline}</div>
        {line && <p className="line-clamp-2 text-xs text-foreground/80 sm:text-sm">{line}</p>}
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
  caption: string; // the drawn pitch's label for screen readers
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
  // A recap on air says it's half-time itself; the break's own label would show through it.
  const fullCard = graphics.some((g) => g.insight.placement === "full_card");

  return (
    <figure className="relative overflow-hidden rounded-xl ring-1 ring-border">
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
        <div className="absolute inset-0 grid place-items-center bg-night/70 p-6 text-center">
          <p className="max-w-xs text-lg font-semibold tracking-tight font-stretch-85%">
            The stream reaches the replay&apos;s start in {waitText(waiting)}.
          </p>
        </div>
      )}
      {breakNow && waiting === 0 && (
        <div className="absolute inset-0 grid place-items-center bg-night/55">
          {!fullCard && <span className="text-4xl font-bold tracking-tight font-stretch-75%">Half-time</span>}
        </div>
      )}
      {/* The panel beside the pitch carries every graphic's text, for screen readers too (P8). */}
      <div aria-hidden>
        {graphics.map((g) => (
          <Graphic key={g.insight.insight_id} shown={g} mode={mode} calm={calm} match={match} />
        ))}
      </div>
    </figure>
  );
}
