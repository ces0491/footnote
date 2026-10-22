"use client";

import { History } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { RuleFrame } from "@/components/pitch/rule-frame";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { clubColour } from "@/lib/club-colour";
import { CATCH_UP_TOPIC, type KeyMoment } from "@/lib/live/catch-up";
import type { Club, Insight, MatchMeta, Player, StateView, TrackingLayout } from "@/lib/live/contract";
import type { Roster } from "@/lib/live/describe";
import { involves, metricFigures, ownFirst, playerLine, undone } from "@/lib/live/fan";
import { cardNote, type Language, langAttribute, LANGUAGES } from "@/lib/live/language";
import type { Shown } from "@/lib/live/playback";
import { METRICS, type Settings } from "@/lib/live/profiles";
import { minuteLabel } from "@/lib/live/timeline";
import { cn } from "@/lib/utils";

import { clubOf, KindIcon } from "./card-kind";
import { CatchUp } from "./catch-up";
import { Evidence } from "./evidence";
import { stateLine } from "./match-state";

/** The catch-up a fan joining mid-match gets, and whether they have it open. */
export interface CatchUpView {
  insight: Insight;
  lang?: Language; // the language its wording is in
  moments: KeyMoment[];
  open: boolean;
  onOpen: () => void;
  onClose: () => void;
}

/** What VAR or the data provider did to a card, in the card's language. */
function Note({ note, lang }: { note: string; lang: Language | undefined }) {
  const said = cardNote(note, lang);
  return (
    <p className={cn("text-sm font-medium", /VAR/.test(note) ? "text-var" : "text-amend")} lang={langAttribute(said.lang)}>
      {said.text}
    </p>
  );
}

/**
 * Who's been on top over the last five minutes, counted by the processor as the cards count it
 * (src/footnote/live/analysis.py, recent_on_top), and the state of play now beneath. The model's
 * estimate of the moment swings with every break; the share of recent minutes moves as the game does.
 */
function OnTop({ view, home, away, own }: { view: StateView; home: Club; away: Club; own: string | null }) {
  const state = view.match_state;
  const [a, b] = ownFirst(home, away, own);
  const shares = state?.recent ?? null;
  const share = (club: Club) => (!shares ? 0 : club.id === home.id ? shares.home : shares.away);
  const leader = state?.team_id === home.id ? home : state?.team_id === away.id ? away : null;
  const other = leader === null ? null : leader.id === home.id ? away : home;
  const label = (club: Club) => `${club.short_name} ${Math.round(share(club) * 100)}%`;
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="font-semibold">Who&apos;s on top</h3>
        <span className="text-xs text-muted-foreground">last 5 minutes</span>
      </div>
      {shares ? (
        <>
          <div className="flex justify-between gap-2 text-sm">
            <span className={cn(a.id === own && "font-semibold")}>
              {a.short_name} <span className="figures">{Math.round(share(a) * 100)}%</span>
            </span>
            <span className={cn(b.id === own && "font-semibold")}>
              <span className="figures">{Math.round(share(b) * 100)}%</span> {b.short_name}
            </span>
          </div>
          <div
            className="flex h-2 gap-0.5 overflow-hidden rounded-full bg-secondary"
            role="img"
            aria-label={`Who's on top over the last five minutes: ${label(a)}, ${label(b)}; the rest neither`}
          >
            <div className="rounded-full" style={{ width: `${share(a) * 100}%`, background: clubColour(a) }} />
            <div className="flex-1" />
            <div className="rounded-full" style={{ width: `${share(b) * 100}%`, background: clubColour(b) }} />
          </div>
        </>
      ) : (
        <p className="text-sm text-muted-foreground">Shows once a minute of the half has been played.</p>
      )}
      {state && <p className="text-sm text-muted-foreground">Now: {stateLine(state.state, leader, other)}</p>}
    </div>
  );
}

/**
 * A fan's side panel: everything the graphics say, as text, and what their settings add. On a phone
 * it is the whole page, a second screen beside the TV. Every card here has reached the fan's
 * playback; nothing later is shown.
 */
export function FanPanel({
  runId,
  match,
  layout,
  view,
  cards,
  catchUp,
  settings,
  roster,
  focus,
}: {
  runId: string;
  match: MatchMeta;
  layout: TrackingLayout | null;
  view: StateView;
  cards: Shown[];
  catchUp: CatchUpView | null;
  settings: Settings;
  roster: Roster;
  focus: Player | null;
}) {
  const clubs = ownFirst(match.home, match.away, settings.club);
  const focusLine = focus ? view.players?.[focus.player_id] : undefined;
  const metric = metricFigures(settings.metric, view, clubs, focus ? { name: focus.name, line: focusLine } : null);
  const analyst = settings.mode === "analyst";
  // The catch-up has a place of its own at the top.
  const listed = cards.filter((s) => s.insight.topic !== CATCH_UP_TOPIC);
  // Cards already here when the panel opened are the match so far; only those that reach the
  // stream after it come in with a movement (none in calm mode).
  const [first] = useState(() => new Set(listed.map((s) => s.insight.insight_id)));
  // Opening the catch-up and closing it each take away the button pressed, so keyboard focus goes to
  // the catch-up's heading as it opens and to the button that reopens it as it closes.
  const heading = useRef<HTMLHeadingElement>(null);
  const reopen = useRef<HTMLButtonElement>(null);
  const focusNext = useRef<"heading" | "reopen" | null>(null);
  const open = catchUp?.open ?? false;
  useEffect(() => {
    const target = focusNext.current === "heading" ? heading.current : focusNext.current === "reopen" ? reopen.current : null;
    focusNext.current = null;
    target?.focus();
  }, [open]);
  return (
    <section aria-labelledby="panel-title" className="overflow-hidden rounded-xl bg-card ring-1 ring-border">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b px-5 py-4">
        <h2 id="panel-title" className="text-xl font-bold tracking-tight font-stretch-75%">
          {analyst ? `Analyst: ${METRICS[settings.metric]}` : "Why it matters"}
        </h2>
        {catchUp && !catchUp.open && (
          <Button
            ref={reopen}
            variant="outline"
            size="sm"
            onClick={() => {
              focusNext.current = "heading";
              catchUp.onOpen();
            }}
          >
            <History aria-hidden /> What you missed
          </Button>
        )}
      </div>
      <div className="space-y-5 px-5 py-5">
        {catchUp?.open && (
          <CatchUp
            runId={runId}
            insight={catchUp.insight}
            lang={catchUp.lang}
            moments={catchUp.moments}
            analyst={analyst}
            onClose={() => {
              focusNext.current = "reopen";
              catchUp.onClose();
            }}
            roster={roster}
            headingRef={heading}
          />
        )}
        {analyst ? (
          <dl className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-4 gap-y-2" aria-label={METRICS[settings.metric]}>
            {metric.clubs.map(({ club, figure }) => (
              <div key={club.id} className="contents">
                <dt className={cn("flex items-center gap-2 text-sm", club.id === settings.club && "font-semibold")}>
                  <span aria-hidden className="size-2.5 rounded-full" style={{ background: clubColour(club) }} />
                  {club.short_name}
                </dt>
                <dd className="text-right text-lg font-semibold figures">{figure}</dd>
              </div>
            ))}
            {metric.player && (
              <div className="contents">
                <dt className="flex items-center gap-2 text-sm font-semibold">
                  <span aria-hidden className="size-2.5 rounded-full ring-2 ring-cite" />
                  {metric.player.name}
                </dt>
                <dd className="text-right text-lg font-semibold figures">{metric.player.figure}</dd>
              </div>
            )}
          </dl>
        ) : (
          <OnTop view={view} home={match.home} away={match.away} own={settings.club} />
        )}
        {focus && (
          <div className="flex gap-3 rounded-lg bg-secondary px-3 py-2.5">
            <span aria-hidden className="mt-1 size-3 shrink-0 rounded-full ring-2 ring-cite" />
            <div className="min-w-0">
              <div className="text-sm font-semibold">
                In focus: {focus.name} ({focus.shirt})
              </div>
              <p className="text-xs text-muted-foreground">{playerLine(focusLine).join(", ") || "No touches yet."}</p>
            </div>
          </div>
        )}
      </div>
      {listed.length === 0 ? (
        <p className="border-t px-5 py-6 text-sm text-muted-foreground">Cards appear here as the moments reach your stream.</p>
      ) : (
        <ol className="border-t" aria-label="Cards">
          {listed.map(({ insight, lang }) => {
            const club = clubOf(insight, match.home, match.away);
            const own = settings.club !== null && club?.id === settings.club;
            const mine = focus !== null && involves(insight, focus.name);
            const state = undone(insight);
            // The card's own wording carries its language; the page's words around it are English.
            const wording = langAttribute(lang);
            return (
              <li
                key={insight.insight_id}
                className={cn(
                  "relative grid grid-cols-[2rem_minmax(0,1fr)] gap-x-3 border-b px-5 py-4 last:border-0",
                  !first.has(insight.insight_id) && "animate-in duration-700 fade-in slide-in-from-top-2",
                )}
              >
                {own && club && <span aria-hidden className="absolute inset-y-0 left-0 w-0.75" style={{ background: clubColour(club) }} />}
                <div className="flex flex-col items-center gap-1.5 pt-0.5">
                  <KindIcon insight={insight} />
                  <span className="text-xs font-semibold text-muted-foreground figures">
                    {minuteLabel(insight.at.minute ?? 0, insight.at.added_minute ?? null)}
                  </span>
                </div>
                <div className="min-w-0 space-y-1.5">
                  <div className="flex items-start justify-between gap-2">
                    <h3 className={cn("text-[17px] leading-snug font-semibold font-stretch-90%", state === "undone" && "line-through decoration-1")} lang={wording}>
                      {insight.card.headline}
                    </h3>
                    {settings.language !== "en" && lang === "en" && (
                      <Badge variant="secondary" className="shrink-0" title={`Not yet in ${LANGUAGES[settings.language]}: the English for now`}>
                        {LANGUAGES.en}
                      </Badge>
                    )}
                  </div>
                  {state !== null && <Note note={state === "undone" ? insight.flag!.reason : "Corrected by the data provider"} lang={lang} />}
                  <p className="font-serif text-[15.5px] leading-relaxed text-foreground/90" lang={wording}>
                    {analyst ? insight.card.analyst : insight.card.casual}
                  </p>
                  {!analyst && layout && insight.topic === "var_decision" && (
                    <RuleFrame runId={runId} insight={insight} match={match} layout={layout} roster={roster} />
                  )}
                  {mine && focusLine && (
                    <p className="text-xs text-muted-foreground">
                      {focus!.name}: {playerLine(focusLine).join(", ")}
                    </p>
                  )}
                  <Evidence runId={runId} insight={insight} roster={roster} />
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
