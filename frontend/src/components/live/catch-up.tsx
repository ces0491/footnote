"use client";

import { Eye, History } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { Insight } from "@/lib/live/contract";
import type { KeyMoment } from "@/lib/live/catch-up";
import type { Roster } from "@/lib/live/describe";

import { Evidence } from "./evidence";

/**
 * "What you missed", for a fan joining a match already under way (docs/experience.md, "Catch-up").
 * The card leaves the score out and the scoreboard hides it too, until the fan asks for it.
 */
export function CatchUp({
  runId,
  insight,
  moments,
  analyst,
  scoreLine,
  scoreShown,
  onShowScore,
  onClose,
  roster,
}: {
  runId: string;
  insight: Insight;
  moments: KeyMoment[];
  analyst: boolean;
  scoreLine: string;
  scoreShown: boolean;
  onShowScore: () => void;
  onClose: () => void;
  roster: Roster;
}) {
  return (
    <section aria-labelledby="catch-up-title" className="space-y-2 rounded-lg border bg-muted/40 p-3">
      <h3 id="catch-up-title" className="flex items-center gap-1.5 font-medium">
        <History aria-hidden className="size-4 text-muted-foreground" />
        {insight.card.headline}
      </h3>
      <p className="text-sm">{insight.card.casual}</p>
      {analyst && <p className="text-sm text-muted-foreground">{insight.card.analyst}</p>}
      {moments.length > 0 && (
        <div>
          <p className="text-xs font-medium text-muted-foreground">Before you joined</p>
          <ul className="mt-1 space-y-0.5 text-sm">
            {moments.map((m) => (
              <li key={m.key} className="flex gap-2">
                <span className="w-16 shrink-0 font-mono text-xs leading-5 tabular-nums text-muted-foreground">{m.minutes}</span>
                <span>{m.label}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <Evidence runId={runId} insight={insight} roster={roster} />
      <div className="flex flex-wrap items-center gap-2">
        {scoreShown ? (
          <p className="text-sm font-medium" aria-live="polite">
            {scoreLine}
          </p>
        ) : (
          <Button variant="outline" size="sm" onClick={onShowScore}>
            <Eye aria-hidden /> Show score
          </Button>
        )}
        <Button size="sm" onClick={onClose}>
          Back to the match
        </Button>
      </div>
    </section>
  );
}
