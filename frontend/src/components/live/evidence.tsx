"use client";

import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { EvidenceResponse, FeedEvent, Insight } from "@/lib/live/contract";
import { describe, type Roster } from "@/lib/live/describe";
import { evidenceSource } from "@/lib/live/shortlist";
import { minuteLabel } from "@/lib/live/timeline";

/** The events behind a card, fetched as they stand when the viewer opens the list. */
export function Evidence({ runId, insight, roster }: { runId: string; insight: Insight; roster: Roster }) {
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
