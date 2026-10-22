"use client";

import { ChevronDown } from "lucide-react";
import { useEffect, useState } from "react";

import { FootnoteMark } from "@/components/brand";
import type { EvidenceResponse, FeedEvent, Insight } from "@/lib/live/contract";
import { describe, type Roster } from "@/lib/live/describe";
import { evidenceSource } from "@/lib/live/shortlist";
import { minuteLabel } from "@/lib/live/timeline";
import { cn } from "@/lib/utils";

/**
 * The events behind a card, as its footnotes, each as it stood at the card's current state (its
 * `shown_seq`): a fan whose stream hasn't reached a correction sees the event as it was, and once the
 * card shows the correction, the list is fetched again and shows the corrected event.
 */
export function Evidence({ runId, insight, roster }: { runId: string; insight: Insight; roster: Roster }) {
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState<{ key: string; events: FeedEvent[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const ids = insight.card.evidence.slice(0, 24);
  const source = evidenceSource(insight);
  const key = `${ids.join(",")}@${insight.shown_seq}`;

  useEffect(() => {
    if (!open || source !== "events" || loaded?.key === key) return;
    let live = true;
    const [list, upto] = key.split("@");
    fetch(`/api/runs/${runId}/events?ids=${list}&upto=${upto}`, { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const body = (await response.json()) as EvidenceResponse;
        if (live) {
          setError(null);
          setLoaded({ key, events: body.events });
        }
      })
      .catch((cause) => live && setError(cause instanceof Error ? cause.message : String(cause)));
    return () => {
      live = false;
    };
  }, [open, source, key, loaded, runId]);

  if (source === "tracking") {
    return (
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <FootnoteMark className="h-3 w-auto text-cite" />
        From the player tracking: no event behind it.
      </p>
    );
  }
  if (source === null) return null;

  const events = loaded?.key === key ? loaded.events : null;
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="-mx-1 inline-flex items-center gap-1.5 rounded-sm px-1 py-0.5 text-xs text-muted-foreground transition-colors outline-none hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50"
      >
        <FootnoteMark className="h-3 w-auto text-cite" />
        Evidence ({ids.length} {ids.length === 1 ? "event" : "events"})
        <ChevronDown aria-hidden className={cn("size-3 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <ol className="mt-2 space-y-1.5 border-l-2 border-cite/60 pl-3 text-xs">
          {error && <li className="text-muted-foreground">Couldn&apos;t load the events: {error}</li>}
          {!error && !events && <li className="text-muted-foreground">Loading…</li>}
          {events?.map((e) => (
            <li key={e.event_id} className="grid grid-cols-[2.5rem_minmax(0,1fr)_auto] items-baseline gap-2">
              <span className="font-semibold text-muted-foreground figures">{minuteLabel(e.minute, e.added_minute)}</span>
              <span>{describe(e, roster).text}</span>
              <code className="text-[11px] text-muted-foreground">{e.event_id}</code>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
