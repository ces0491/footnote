import { clubColour } from "@/lib/club-colour";
import type { Club, TeamStats } from "@/lib/live/contract";
import { NBSP } from "@/lib/live/describe";

function percent(value: number | null): string {
  return value === null ? "–" : `${Math.round(value * 100)}%`;
}

/** A figure with its unit, joined by a non-breaking space so the unit never wraps away from it. */
function measure(value: number | null | undefined, unit: string, digits = 1): string {
  if (value === null || value === undefined) return "–";
  return unit ? `${value.toFixed(digits)}${NBSP}${unit}` : value.toFixed(digits);
}

interface Row {
  label: string;
  home: string;
  away: string;
  // Each side's share of the bar; omitted for rows where a bar would mislead.
  shares?: [number, number];
}

function rows(h: TeamStats, a: TeamStats): Row[] {
  const count = (label: string, key: keyof TeamStats): Row => {
    const hv = Number(h[key] ?? 0);
    const av = Number(a[key] ?? 0);
    return { label, home: String(hv), away: String(av), shares: hv + av > 0 ? [hv, av] : undefined };
  };
  return [
    count("Shots", "shots"),
    count("On target", "on_target"),
    {
      label: "Passes completed",
      home: `${h.passes_completed}/${h.passes}`,
      away: `${a.passes_completed}/${a.passes}`,
    },
    { label: "Pass accuracy", home: percent(h.pass_accuracy), away: percent(a.pass_accuracy) },
    { label: "Average pass length", home: measure(h.pass_length, "m"), away: measure(a.pass_length, "m") },
    { label: "Average pass difficulty", home: measure(h.pass_difficulty, "", 2), away: measure(a.pass_difficulty, "", 2) },
    { label: "Distance covered", home: measure(h.distance_km, "km"), away: measure(a.distance_km, "km") },
    { label: "Fastest shot", home: measure(h.top_shot_kmh, "km/h", 0), away: measure(a.top_shot_kmh, "km/h", 0) },
    count("Corners", "corners"),
    count("Fouls", "fouls"),
    count("Offsides", "offsides"),
    count("Yellow cards", "yellow_cards"),
    count("Red cards", "red_cards"),
  ];
}

export function StatsPanel({ home, away, stats }: { home: Club; away: Club; stats: Record<string, TeamStats> }) {
  const h = stats[home.id];
  const a = stats[away.id];
  if (!h || !a) return null;
  const homeShare = h.possession ?? 0.5;
  const [homeColour, awayColour] = [clubColour(home), clubColour(away)];
  return (
    <section aria-labelledby="stats-title" className="overflow-hidden rounded-xl bg-card ring-1 ring-border">
      <h2 id="stats-title" className="border-b px-5 py-4 text-xl font-bold tracking-tight font-stretch-75%">
        Match stats
      </h2>
      <div className="space-y-5 p-5">
        <div>
          <div className="mb-2 flex items-end justify-between gap-2">
            <span className="text-3xl leading-none font-bold figures">{percent(h.possession)}</span>
            <span className="text-sm text-muted-foreground">Possession</span>
            <span className="text-3xl leading-none font-bold figures">{percent(a.possession)}</span>
          </div>
          <div className="flex h-2 gap-0.5" role="img" aria-label={`Possession ${percent(h.possession)} to ${percent(a.possession)}`}>
            <div className="rounded-full" style={{ width: `${homeShare * 100}%`, background: homeColour }} />
            <div className="flex-1 rounded-full" style={{ background: awayColour }} />
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Share of passes, the broadcast convention. Difficulty is one minus the modelled chance a pass reaches its target; distance
            comes from the tracking.
          </p>
        </div>
        <dl className="divide-y">
          {rows(h, a).map((row) => (
            // The label comes first, as a description list has it, and sits between the figures.
            <div key={row.label} className="grid grid-cols-[5.5rem_minmax(0,1fr)_5.5rem] items-center gap-3 py-2.5 text-sm">
              <dt className="col-start-2 row-start-1 text-center text-muted-foreground">
                {row.label}
                {row.shares && (
                  <span className="mt-1.5 flex h-1 gap-0.5" aria-hidden>
                    <span className="rounded-full" style={{ flexGrow: row.shares[0], background: homeColour }} />
                    <span className="rounded-full" style={{ flexGrow: row.shares[1], background: awayColour }} />
                  </span>
                )}
              </dt>
              <dd className="col-start-1 row-start-1 font-semibold whitespace-nowrap figures">{row.home}</dd>
              <dd className="col-start-3 row-start-1 text-right font-semibold whitespace-nowrap figures">{row.away}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}
