import type { CSSProperties } from "react";

import { clubColour } from "@/lib/club-colour";
import type { Club, MatchState, MatchStateKind, StateSpell } from "@/lib/live/contract";
import { clockLabel } from "@/lib/live/timeline";

const PERIOD_SECONDS = 45 * 60;
// Spells that are no side's: neither in control hatched, evenly matched plain, both in grey, as no
// club's colour is grey.
const CHAOS = "repeating-linear-gradient(90deg, var(--muted-foreground) 0 1.5px, transparent 1.5px 4px)";
const BALANCED = "color-mix(in oklab, var(--muted-foreground) 30%, transparent)";

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
  if (spell.state === "balanced" || !club) return { background: BALANCED };
  const colour = clubColour(club);
  if (spell.state === "control") return { background: colour };
  // Pressure and breaks share the side's colour, told apart by stripes of different widths.
  const stripe = spell.state === "pressure" ? 6 : 3;
  return {
    background: `repeating-linear-gradient(135deg, ${colour} 0 ${stripe}px, color-mix(in oklab, ${colour} 40%, transparent) ${stripe}px ${2 * stripe}px)`,
  };
}

function Half({ period, spells, home, away }: { period: 1 | 2; spells: StateSpell[]; home: Club; away: Club }) {
  const own = spells.filter((s) => s.period === period);
  const length = Math.max(PERIOD_SECONDS, ...own.map((s) => s.end + 1));
  return (
    <div className="grid grid-cols-[4rem_minmax(0,1fr)] items-center gap-3 text-xs">
      <span className="text-muted-foreground">{period === 1 ? "1st half" : "2nd half"}</span>
      <div className="relative h-5 overflow-hidden rounded-sm bg-secondary" aria-hidden>
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
    ["Control", { background: clubColour(home) }],
    ["Pinned back", fill({ period: 1, state: "pressure", team_id: home.id, start: 0, end: 0 }, home)],
    ["Break", fill({ period: 1, state: "transition", team_id: away.id, start: 0, end: 0 }, away)],
    ["Neither in control", { background: CHAOS }],
    ["Even", { background: BALANCED }],
  ];
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground" aria-hidden>
      {items.map(([label, style]) => (
        <li key={label} className="flex items-center gap-1.5">
          <span className="size-3 rounded-[3px]" style={style} />
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
    <section aria-labelledby="state-title" className="overflow-hidden rounded-xl bg-card ring-1 ring-border">
      <div className="border-b px-5 py-4">
        <h2 id="state-title" className="text-xl font-bold tracking-tight font-stretch-75%">
          Match state
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">Estimated from the events by a model that runs a few seconds behind play.</p>
      </div>
      <div className="space-y-5 p-5">
        {state ? (
          <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <p className="text-2xl leading-tight font-bold tracking-tight font-stretch-75%">{stateLine(state.state, club, other)}</p>
            <span className="flex items-center gap-2 text-sm text-muted-foreground">
              <span className="rounded-sm bg-secondary px-2 py-0.5 font-semibold text-foreground figures">{Math.round(state.confidence * 100)}% likely</span>
              as of {clockLabel({ period: state.period === 1 ? 1 : 2, t: state.second })}
            </span>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">The first estimate comes a few seconds after kick-off.</p>
        )}
        <div>
          <div className="mb-2 flex justify-between gap-2 text-sm">
            <span>
              {home.short_name} <span className="font-semibold figures">{Math.round(homeShare * 100)}%</span>
            </span>
            <span className="text-muted-foreground">Chance on top now</span>
            <span>
              <span className="font-semibold figures">{Math.round(awayShare * 100)}%</span> {away.short_name}
            </span>
          </div>
          <div
            className="flex h-2 gap-0.5 overflow-hidden rounded-full bg-secondary"
            role="img"
            aria-label={`Chance each side is on top: ${home.short_name} ${Math.round(homeShare * 100)}%, ${away.short_name} ${Math.round(awayShare * 100)}%; the rest neither`}
          >
            <div className="rounded-full" style={{ width: `${homeShare * 100}%`, background: clubColour(home) }} />
            <div className="flex-1" />
            <div className="rounded-full" style={{ width: `${awayShare * 100}%`, background: clubColour(away) }} />
          </div>
        </div>
        <div className="space-y-2">
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
      </div>
    </section>
  );
}
