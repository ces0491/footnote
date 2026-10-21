"use client";

import { History, MonitorPlay } from "lucide-react";
import { useEffect, useRef } from "react";

import { RuleFrame } from "@/components/pitch/rule-frame";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CATCH_UP_TOPIC, type KeyMoment } from "@/lib/live/catch-up";
import type { Club, Insight, MatchMeta, Player, StateView, TrackingLayout } from "@/lib/live/contract";
import type { Roster } from "@/lib/live/describe";
import { involves, metricFigures, ownFirst, playerLine, undone } from "@/lib/live/fan";
import { type Language, langAttribute, LANGUAGES } from "@/lib/live/language";
import type { Shown } from "@/lib/live/playback";
import { METRICS, type Settings } from "@/lib/live/profiles";
import { minuteLabel } from "@/lib/live/timeline";
import { cn } from "@/lib/utils";

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
    <div className="space-y-1.5">
      {shares ? (
        <>
          <p className="text-sm text-muted-foreground">Who&apos;s on top, last 5 minutes</p>
          <div className="flex justify-between gap-2 text-sm">
            <span className={cn("tabular-nums", a.id === own && "font-semibold")}>{label(a)}</span>
            <span className={cn("tabular-nums", b.id === own && "font-semibold")}>
              {Math.round(share(b) * 100)}% {b.short_name}
            </span>
          </div>
          <div
            className="flex h-2.5 overflow-hidden rounded-full bg-muted"
            role="img"
            aria-label={`Who's on top over the last five minutes: ${label(a)}, ${label(b)}; the rest neither`}
          >
            <div style={{ width: `${share(a) * 100}%`, background: a.colours[0] }} />
            <div className="flex-1" />
            <div style={{ width: `${share(b) * 100}%`, background: b.colours[0] }} />
          </div>
        </>
      ) : (
        <p className="text-sm text-muted-foreground">Who&apos;s on top shows once a minute of the half has been played.</p>
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
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle>{analyst ? `Analyst · ${METRICS[settings.metric]}` : "Why it matters"}</CardTitle>
        {catchUp && !catchUp.open && (
          <Button
            ref={reopen}
            variant="ghost"
            size="sm"
            className="h-7"
            onClick={() => {
              focusNext.current = "heading";
              catchUp.onOpen();
            }}
          >
            <History aria-hidden /> What you missed
          </Button>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
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
          <dl className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 rounded-lg bg-muted/60 px-3 py-2 text-sm" aria-label={METRICS[settings.metric]}>
            {metric.clubs.map(({ club, figure }) => (
              <div key={club.id} className="contents">
                <dt className={cn(club.id === settings.club && "font-semibold")}>{club.short_name}</dt>
                <dd className="text-right tabular-nums">{figure}</dd>
              </div>
            ))}
            {metric.player && (
              <div className="contents">
                <dt className="font-semibold">{metric.player.name}</dt>
                <dd className="text-right tabular-nums">{metric.player.figure}</dd>
              </div>
            )}
          </dl>
        ) : (
          <OnTop view={view} home={match.home} away={match.away} own={settings.club} />
        )}
        {focus && (
          <div className="rounded-lg border px-3 py-2 text-sm">
            <div className="font-medium">
              In focus: {focus.name} ({focus.shirt})
            </div>
            <p className="text-xs text-muted-foreground">{playerLine(focusLine).join(" · ") || "No touches yet."}</p>
          </div>
        )}
        {listed.length === 0 ? (
          <p className="text-sm text-muted-foreground">Cards appear here as the moments reach your stream.</p>
        ) : (
          <ol className="space-y-3" aria-label="Cards">
            {listed.map(({ insight, lang }) => {
              const own = settings.club !== null && Object.values(insight.fields).includes(clubs[0].short_name);
              const mine = focus !== null && involves(insight, focus.name);
              const Icon = insight.kind === "correction" ? History : insight.kind === "rule_call" ? MonitorPlay : null;
              // The card's own wording carries its language; the page's words around it are English.
              const wording = langAttribute(lang);
              return (
                <li key={insight.insight_id} className={cn("space-y-1 rounded-lg border p-3", own && "border-l-4")} style={own ? { borderLeftColor: clubs[0].colours[0] } : undefined}>
                  <div className="flex items-start justify-between gap-2">
                    <div className={cn("font-medium", undone(insight) === "undone" && "line-through decoration-1")} lang={wording}>
                      {Icon && <Icon aria-hidden className="mr-1.5 inline size-4 align-[-2px] text-muted-foreground" />}
                      {insight.card.headline}
                    </div>
                    <div className="flex shrink-0 gap-1">
                      {settings.language !== "en" && lang === "en" && (
                        <Badge variant="secondary" title={`Not yet in ${LANGUAGES[settings.language]}: the English for now`}>
                          {LANGUAGES.en}
                        </Badge>
                      )}
                      <Badge variant="outline" className="font-mono tabular-nums">
                        {minuteLabel(insight.at.minute ?? 0, insight.at.added_minute ?? null)}
                      </Badge>
                    </div>
                  </div>
                  {undone(insight) === "undone" && (
                    <p className="text-sm font-medium text-amber-700 dark:text-amber-400">{insight.flag!.reason}</p>
                  )}
                  {undone(insight) === "corrected" && (
                    <p className="text-sm font-medium text-amber-700 dark:text-amber-400">Corrected by the data provider</p>
                  )}
                  <p className="text-sm" lang={wording}>
                    {analyst ? insight.card.analyst : insight.card.casual}
                  </p>
                  {!analyst && layout && insight.topic === "var_decision" && (
                    <RuleFrame runId={runId} insight={insight} match={match} layout={layout} roster={roster} />
                  )}
                  {mine && focusLine && (
                    <p className="text-xs text-muted-foreground">
                      {focus!.name}: {playerLine(focusLine).join(" · ")}
                    </p>
                  )}
                  <Evidence runId={runId} insight={insight} roster={roster} />
                </li>
              );
            })}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
