"use client";

import { ChevronDown, ChevronRight, History } from "lucide-react";
import { useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { Clock, EvidenceResponse, FeedEvent, Insight } from "@/lib/live/contract";
import { describe, type Roster } from "@/lib/live/describe";
import { corrections, evidenceSource, provenanceLabel, shortlist } from "@/lib/live/shortlist";
import { minuteLabel } from "@/lib/live/timeline";

function Evidence({ runId, insight, roster }: { runId: string; insight: Insight; roster: Roster }) {
  const [open, setOpen] = useState(false);
  const [events, setEvents] = useState<FeedEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const ids = insight.card.evidence.slice(0, 24);
  const source = evidenceSource(insight);
  if (source === "tracking") return <p className="text-xs text-muted-foreground">From the player tracking: no event behind it.</p>;
  if (source === null) return null;

  async function toggle() {
    setOpen(!open);
    if (events || open) return;
    try {
      const response = await fetch(`/api/runs/${runId}/events?ids=${ids.join(",")}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setEvents(((await response.json()) as EvidenceResponse).events);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }

  const Icon = open ? ChevronDown : ChevronRight;
  return (
    <div>
      <Button variant="ghost" size="sm" className="-ml-2 h-7 px-2" onClick={toggle} aria-expanded={open}>
        <Icon aria-hidden /> Evidence ({ids.length} {ids.length === 1 ? "event" : "events"})
      </Button>
      {open && (
        <ul className="mt-1 space-y-1 border-l pl-3 text-xs text-muted-foreground">
          {error && <li>Couldn&apos;t load the events: {error}</li>}
          {!error && !events && <li>Loading…</li>}
          {events?.map((e) => (
            <li key={e.event_id} className="flex gap-2">
              <span className="w-12 shrink-0 font-mono tabular-nums">{minuteLabel(e.minute, e.added_minute)}</span>
              <span>{describe(e, roster).text}</span>
              <code className="ml-auto shrink-0">{e.event_id}</code>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Item({ runId, insight, position, roster }: { runId: string; insight: Insight; position: number; roster: Roster }) {
  return (
    <li className="space-y-1.5 rounded-lg border p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="font-medium">
          <span className="mr-2 text-muted-foreground tabular-nums">{position}</span>
          {insight.card.headline}
        </div>
        <span className="shrink-0 text-xs text-muted-foreground tabular-nums" title="Rank, from the match-state model">
          rank {insight.rank.toFixed(2)}
        </span>
      </div>
      <p className="text-sm">{insight.card.casual}</p>
      <p className="text-xs text-muted-foreground">{insight.card.analyst}</p>
      <p className="text-xs text-muted-foreground">
        <span className="font-medium text-foreground">Why it&apos;s here: </span>
        {insight.reason}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={insight.source === "agent" ? "secondary" : "outline"}>{provenanceLabel(insight)}</Badge>
        {insight.agent_note && <span className="text-xs text-muted-foreground">{insight.agent_note}</span>}
      </div>
      <Evidence runId={runId} insight={insight} roster={roster} />
    </li>
  );
}

export function Shortlist({
  runId,
  insights,
  clock,
  roster,
}: {
  runId: string;
  insights: Record<string, Insight>;
  clock: Clock | null;
  roster: Roster;
}) {
  const all = Object.values(insights);
  const top = shortlist(all, clock ? { period: clock.period, t: clock.t } : null);
  const alerts = corrections(all);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Producer shortlist</CardTitle>
        <CardDescription>
          The strongest moments still current, ranked with the match-state model. Each card shows its template wording
          until an agent&apos;s checked draft replaces it.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {alerts.length > 0 && (
          <Alert>
            <History aria-hidden />
            <AlertTitle>Corrections</AlertTitle>
            <AlertDescription>
              <ul className="space-y-1">
                {alerts.map((i) => (
                  <li key={i.insight_id}>
                    {i.kind === "correction" ? (
                      <span className="font-medium">{i.card.casual}</span>
                    ) : (
                      <span>
                        <span className="font-medium">{i.card.headline}</span>: {i.flag?.reason}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        )}
        {top.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing on the shortlist yet.</p>
        ) : (
          <ol className="space-y-3">
            {top.map((insight, n) => (
              <Item key={insight.insight_id} runId={runId} insight={insight} position={n + 1} roster={roster} />
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
