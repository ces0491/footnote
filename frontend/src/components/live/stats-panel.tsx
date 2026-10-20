import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Club, TeamStats } from "@/lib/live/contract";

function percent(value: number | null): string {
  return value === null ? "–" : `${Math.round(value * 100)}%`;
}

function measure(value: number | null | undefined, unit: string, digits = 1): string {
  return value === null || value === undefined ? "–" : `${value.toFixed(digits)}${unit}`;
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
    { label: "Average pass length", home: measure(h.pass_length, " m"), away: measure(a.pass_length, " m") },
    { label: "Average pass difficulty", home: measure(h.pass_difficulty, "", 2), away: measure(a.pass_difficulty, "", 2) },
    { label: "Distance covered", home: measure(h.distance_km, " km"), away: measure(a.distance_km, " km") },
    { label: "Fastest shot", home: measure(h.top_shot_kmh, " km/h", 0), away: measure(a.top_shot_kmh, " km/h", 0) },
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
  return (
    <Card>
      <CardHeader>
        <CardTitle>Match stats</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <div className="mb-1.5 flex justify-between text-sm">
            <span className="font-medium tabular-nums">{percent(h.possession)}</span>
            <span className="text-muted-foreground">Possession</span>
            <span className="font-medium tabular-nums">{percent(a.possession)}</span>
          </div>
          <div className="flex h-2.5 overflow-hidden rounded-full bg-muted" role="img" aria-label={`Possession ${percent(h.possession)} to ${percent(a.possession)}`}>
            <div style={{ width: `${homeShare * 100}%`, background: home.colours[0] }} />
            <div style={{ width: `${(1 - homeShare) * 100}%`, background: away.colours[0] }} />
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Share of passes, the broadcast convention. Difficulty is one minus the modelled chance a pass reaches its
            target; distance comes from the tracking.
          </p>
        </div>
        <dl className="divide-y">
          {rows(h, a).map((row) => (
            <div key={row.label} className="grid grid-cols-[4rem_1fr_4rem] items-center gap-3 py-2 text-sm">
              <dd className="font-medium tabular-nums">{row.home}</dd>
              <dt className="text-center text-muted-foreground">
                {row.label}
                {row.shares && (
                  <span className="mt-1 flex h-1 overflow-hidden rounded-full bg-muted" aria-hidden>
                    <span style={{ flexGrow: row.shares[0], background: home.colours[0] }} />
                    <span style={{ flexGrow: row.shares[1], background: away.colours[0] }} />
                  </span>
                )}
              </dt>
              <dd className="text-right font-medium tabular-nums">{row.away}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}
