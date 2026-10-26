"use client";

import { History } from "lucide-react";
import type { Ref } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { KeyMoment } from "@/lib/live/catch-up";
import type { Insight } from "@/lib/live/contract";
import type { Roster } from "@/lib/live/describe";
import { type Language, langAttribute, LANGUAGES } from "@/lib/live/language";

import { Evidence } from "./evidence";

/**
 * "What you missed", for a fan joining a match already under way (docs/experience.md, "Catch-up").
 * The card names the goals and leaves the score to the scoreboard. Its heading takes keyboard focus
 * when the fan opens it (`headingRef`). Wording still in English for a fan reading another language
 * is marked, as the panel's graphics are.
 */
export function CatchUp({
  runId,
  insight,
  lang,
  reading = "en",
  moments,
  analyst,
  onClose,
  roster,
  headingRef,
}: {
  runId: string;
  insight: Insight;
  lang?: Language; // the language its wording is in
  reading?: Language; // the language the fan reads in
  moments: KeyMoment[];
  analyst: boolean;
  onClose: () => void;
  roster: Roster;
  headingRef?: Ref<HTMLHeadingElement>;
}) {
  const wording = langAttribute(lang);
  return (
    <section aria-labelledby="catch-up-title" className="space-y-3 rounded-lg bg-secondary p-4">
      <div className="flex items-start justify-between gap-2">
        <h3
          id="catch-up-title"
          ref={headingRef}
          tabIndex={-1}
          lang={wording}
          className="flex items-center gap-2 rounded-sm text-lg leading-tight font-bold tracking-tight font-stretch-75% outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
        >
          <History aria-hidden className="size-4 shrink-0 text-muted-foreground" />
          {insight.card.headline}
        </h3>
        {reading !== "en" && lang === "en" && (
          <Badge variant="secondary" className="shrink-0" title={`Not yet in ${LANGUAGES[reading]}: the English for now`}>
            {LANGUAGES.en}
          </Badge>
        )}
      </div>
      <p className="font-serif text-[15.5px] leading-relaxed" lang={wording}>
        {insight.card.casual}
      </p>
      {analyst && (
        <p className="font-serif text-sm leading-relaxed text-muted-foreground" lang={wording}>
          {insight.card.analyst}
        </p>
      )}
      {moments.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-muted-foreground">Before you joined</p>
          <ul className="mt-2 space-y-1 border-l border-edge pl-3 text-sm">
            {moments.map((m) => (
              <li key={m.key} className="grid grid-cols-[4.25rem_minmax(0,1fr)] gap-2" lang={langAttribute(m.lang)}>
                <span className="font-semibold text-muted-foreground figures">{m.minutes}</span>
                <span>{m.label}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
        <Evidence runId={runId} insight={insight} roster={roster} />
        <Button size="sm" onClick={onClose}>
          Back to the match
        </Button>
      </div>
    </section>
  );
}
