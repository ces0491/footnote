"use client";

import { History } from "lucide-react";
import type { Ref } from "react";

import { Button } from "@/components/ui/button";
import type { Insight } from "@/lib/live/contract";
import type { KeyMoment } from "@/lib/live/catch-up";
import type { Roster } from "@/lib/live/describe";
import { type Language, langAttribute } from "@/lib/live/language";

import { Evidence } from "./evidence";

/**
 * "What you missed", for a fan joining a match already under way (docs/experience.md, "Catch-up").
 * The card names the goals and leaves the score to the scoreboard. Its heading takes keyboard focus
 * when the fan opens it (`headingRef`).
 */
export function CatchUp({
  runId,
  insight,
  lang,
  moments,
  analyst,
  onClose,
  roster,
  headingRef,
}: {
  runId: string;
  insight: Insight;
  lang?: Language; // the language its wording is in
  moments: KeyMoment[];
  analyst: boolean;
  onClose: () => void;
  roster: Roster;
  headingRef?: Ref<HTMLHeadingElement>;
}) {
  const wording = langAttribute(lang);
  return (
    <section aria-labelledby="catch-up-title" className="space-y-2 rounded-lg border bg-muted/40 p-3">
      <h3
        id="catch-up-title"
        ref={headingRef}
        tabIndex={-1}
        lang={wording}
        className="flex items-center gap-1.5 rounded-sm font-medium outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
      >
        <History aria-hidden className="size-4 text-muted-foreground" />
        {insight.card.headline}
      </h3>
      <p className="text-sm" lang={wording}>
        {insight.card.casual}
      </p>
      {analyst && (
        <p className="text-sm text-muted-foreground" lang={wording}>
          {insight.card.analyst}
        </p>
      )}
      {moments.length > 0 && (
        <div>
          <p className="text-xs font-medium text-muted-foreground">Before you joined</p>
          <ul className="mt-1 space-y-0.5 text-sm">
            {moments.map((m) => (
              <li key={m.key} className="flex gap-2" lang={langAttribute(m.lang)}>
                <span className="w-16 shrink-0 font-mono text-xs leading-5 tabular-nums text-muted-foreground">{m.minutes}</span>
                <span>{m.label}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <Evidence runId={runId} insight={insight} roster={roster} />
      <Button size="sm" onClick={onClose}>
        Back to the match
      </Button>
    </section>
  );
}
