import type { CSSProperties } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { Club, MatchState, MatchStateKind, StateSpell } from "@/lib/live/contract";
import { clockLabel } from "@/lib/live/timeline";

const PERIOD_SECONDS = 45 * 60;
const CHAOS = "#d97706";
const BALANCED = "var(--muted-foreground)";

/** What a state says about the match, in a line. */
export function stateLine(state: MatchStateKind, club: Club | null, other: Club | null): string {
  const side = club?.short_name ?? "One side";
  switch (state) {
    case "control":
      return `${side} in control`;
    case "pressure":
      return `${side} pinning ${other?.short_name ?? "the other"} back`;
    case "transition":
      return `${side} on the break`;
    case "chaos":
      return "Neither side in control";
    case "balanced":
      return "Evenly matched";
  }
}

function clubs(teamId: string | null, home: Club, away: Club): [Club | null, Club | null] {
  if (teamId === home.id) return [home, away];
  if (teamId === away.id) return [away, home];
  return [null, null];
}

function fill(spell: StateSpell, club: Club | null): CSSProperties {
  if (spell.state === "chaos") return { background: CHAOS };
  if (spell.state === "balanced" || !club) return { background: BALANCED, opacity: 0.35 };
  const colour = club.colours[0];
  if (spell.state === "control") return { background: colour };
  // Pressure and breaks share the side's colour, told apart by stripes of different widths.
  const stripe = spell.state === "pressure" ? 6 : 3;
  return {
    background: `repeating-linear-gradient(135deg, ${colour} 0 ${stripe}px, color-mix(in oklab, ${colour} 45%, transparent) ${stripe}px ${2 * stripe}px)`,
  };
}

function Half({ period, spells, home, away }: { period: 1 | 2; spells: StateSpell[]; home: Club; away: Club }) {
  const own = spells.filter((s) => s.period === period);
  const length = Math.max(PERIOD_SECONDS, ...own.map((s) => s.end + 1));
  return (
    <div className="grid grid-cols-[3.5rem_1fr] items-center gap-2 text-xs">
      <span className="text-muted-foreground">{period === 1 ? "1st half" : "2nd half"}</span>
      <div className="relative h-4 overflow-hidden rounded bg-muted" aria-hidden>
        {own.map((spell, i) => {
          const next = own[i + 1];
          const stop = next ? next.start : spell.end + 1;
          const [club] = clubs(spell.team_id, home, away);
          return (
            <span
              key={`${spell.period}-${spell.start}`}
              className="absolute inset-y-0"
              style={{ left: `${(spell.start / length) * 100}%`, width: `${((stop - spell.start) / length) * 100}%`, ...fill(spell, club) }}
            />
          );
        })}
      </div>
    </div>
  );
}

function Legend({ home, away }: { home: Club; away: Club }) {
  const items: [string, CSSProperties][] = [
    ["Control", { background: home.colours[0] }],
    ["Pinned back", fill({ period: 1, state: "pressure", team_id: home.id, start: 0, end: 0 }, home)],
    ["Break", fill({ period: 1, state: "transition", team_id: away.id, start: 0, end: 0 }, away)],
    ["Neither in control", { background: CHAOS }],
    ["Even", { background: BALANCED, opacity: 0.35 }],
  ];
  return (
    <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground" aria-hidden>
      {items.map(([label, style]) => (
        <li key={label} className="flex items-center gap-1.5">
          <span className="size-3 rounded-sm" style={style} />
          {label}
        </li>
      ))}
    </ul>
  );
}

export function MatchStatePanel({
  home,
  away,
  state,
  timeline,
}: {
  home: Club;
  away: Club;
  state: MatchState | null | undefined;
  timeline: StateSpell[];
}) {
  const [club, other] = state ? clubs(state.team_id, home, away) : [null, null];
  const homeShare = state ? state.on_top.home : 0;
  const awayShare = state ? state.on_top.away : 0;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Match state</CardTitle>
        <CardDescription>Estimated from the events by a model that runs a few seconds behind play.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {state ? (
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-lg font-semibold">{stateLine(state.state, club, other)}</p>
            <span className="text-sm text-muted-foreground">
              <Badge variant="outline" className="mr-2 tabular-nums">
                {Math.round(state.confidence * 100)}% likely
              </Badge>
              as of {clockLabel({ period: state.period === 1 ? 1 : 2, t: state.second })}
            </span>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">The first estimate comes a few seconds after kick-off.</p>
        )}
        <div>
          <div className="mb-1.5 flex justify-between text-sm">
            <span className="tabular-nums">
              {home.short_name} {Math.round(homeShare * 100)}%
            </span>
            <span className="text-muted-foreground">On top</span>
            <span className="tabular-nums">
              {Math.round(awayShare * 100)}% {away.short_name}
            </span>
          </div>
          <div
            className="flex h-2.5 overflow-hidden rounded-full bg-muted"
            role="img"
            aria-label={`Chance each side is on top: ${home.short_name} ${Math.round(homeShare * 100)}%, ${away.short_name} ${Math.round(awayShare * 100)}%; the rest neither`}
          >
            <div style={{ width: `${homeShare * 100}%`, background: home.colours[0] }} />
            <div className="flex-1" />
            <div style={{ width: `${awayShare * 100}%`, background: away.colours[0] }} />
          </div>
        </div>
        <div className="space-y-1.5">
          <Half period={1} spells={timeline} home={home} away={away} />
          <Half period={2} spells={timeline} home={home} away={away} />
        </div>
        <Legend home={home} away={away} />
        <ol className="sr-only">
          {timeline.map((spell) => {
            const [c, o] = clubs(spell.team_id, home, away);
            const period = spell.period === 1 ? 1 : 2;
            return (
              <li key={`${spell.period}-${spell.start}`}>
                {clockLabel({ period, t: spell.start })} to {clockLabel({ period, t: spell.end })}: {stateLine(spell.state, c, o)}
              </li>
            );
          })}
        </ol>
      </CardContent>
    </Card>
  );
}
