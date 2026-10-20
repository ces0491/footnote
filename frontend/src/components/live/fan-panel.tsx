"use client";

import { History, MonitorPlay } from "lucide-react";

import { RuleFrame } from "@/components/pitch/rule-frame";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Club, MatchMeta, Player, StateView, TrackingLayout } from "@/lib/live/contract";
import type { Roster } from "@/lib/live/describe";
import { involves, metricFigures, ownFirst, playerLine, undone } from "@/lib/live/fan";
import type { Shown } from "@/lib/live/playback";
import { METRICS, type Settings } from "@/lib/live/profiles";
import { minuteLabel } from "@/lib/live/timeline";
import { cn } from "@/lib/utils";

import { Evidence } from "./evidence";
import { stateLine } from "./match-state";

function OnTop({ view, home, away, own }: { view: StateView; home: Club; away: Club; own: string | null }) {
  const state = view.match_state;
  const [a, b] = ownFirst(home, away, own);
  const share = (club: Club) => (!state ? 0 : club.id === home.id ? state.on_top.home : state.on_top.away);
  const leader = state?.team_id === home.id ? home : state?.team_id === away.id ? away : null;
  const other = leader === null ? null : leader.id === home.id ? away : home;
  const label = (club: Club) => `${club.short_name} ${Math.round(share(club) * 100)}%`;
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-sm">
        <span className={cn("tabular-nums", a.id === own && "font-semibold")}>{label(a)}</span>
        <span className="text-muted-foreground">Who&apos;s on top</span>
        <span className={cn("tabular-nums", b.id === own && "font-semibold")}>
          {Math.round(share(b) * 100)}% {b.short_name}
        </span>
      </div>
      <div
        className="flex h-2.5 overflow-hidden rounded-full bg-muted"
        role="img"
        aria-label={`Who's on top: ${label(a)}, ${label(b)}; the rest neither`}
      >
        <div style={{ width: `${share(a) * 100}%`, background: a.colours[0] }} />
        <div className="flex-1" />
        <div style={{ width: `${share(b) * 100}%`, background: b.colours[0] }} />
      </div>
      {state && <p className="text-sm text-muted-foreground">{stateLine(state.state, leader, other)}</p>}
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
  settings,
  roster,
  focus,
}: {
  runId: string;
  match: MatchMeta;
  layout: TrackingLayout | null;
  view: StateView;
  cards: Shown[];
  settings: Settings;
  roster: Roster;
  focus: Player | null;
}) {
  const clubs = ownFirst(match.home, match.away, settings.club);
  const focusLine = focus ? view.players?.[focus.player_id] : undefined;
  const metric = metricFigures(settings.metric, view, clubs, focus ? { name: focus.name, line: focusLine } : null);
  const analyst = settings.mode === "analyst";
  return (
    <Card>
      <CardHeader>
        <CardTitle>{analyst ? `Analyst · ${METRICS[settings.metric]}` : "Why it matters"}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
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
        {cards.length === 0 ? (
          <p className="text-sm text-muted-foreground">Cards appear here as the moments reach your stream.</p>
        ) : (
          <ol className="space-y-3" aria-label="Cards">
            {cards.map(({ insight }) => {
              const own = settings.club !== null && Object.values(insight.fields).includes(clubs[0].short_name);
              const mine = focus !== null && involves(insight, focus.name);
              const Icon = insight.kind === "correction" ? History : insight.kind === "rule_call" ? MonitorPlay : null;
              return (
                <li key={insight.insight_id} className={cn("space-y-1 rounded-lg border p-3", own && "border-l-4")} style={own ? { borderLeftColor: clubs[0].colours[0] } : undefined}>
                  <div className="flex items-start justify-between gap-2">
                    <div className={cn("font-medium", undone(insight) === "undone" && "line-through decoration-1")}>
                      {Icon && <Icon aria-hidden className="mr-1.5 inline size-4 align-[-2px] text-muted-foreground" />}
                      {insight.card.headline}
                    </div>
                    <Badge variant="outline" className="shrink-0 font-mono tabular-nums">
                      {minuteLabel(insight.at.minute ?? 0, insight.at.added_minute ?? null)}
                    </Badge>
                  </div>
                  {undone(insight) === "undone" && (
                    <p className="text-sm font-medium text-amber-700 dark:text-amber-400">{insight.flag!.reason}</p>
                  )}
                  {undone(insight) === "corrected" && (
                    <p className="text-sm font-medium text-amber-700 dark:text-amber-400">Corrected by the data provider</p>
                  )}
                  <p className="text-sm">{analyst ? insight.card.analyst : insight.card.casual}</p>
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
