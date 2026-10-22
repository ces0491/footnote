"use client";

import { Pause, Play } from "lucide-react";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import type { EventMessage, MatchMeta, StateView } from "@/lib/live/contract";
import { NBSP, type Roster } from "@/lib/live/describe";
import { atDetail, cardLines, type Detail, DETAILS, eventLines, merged, nextSaying, type Pace, PACES, type Part } from "@/lib/live/described";
import type { Shown } from "@/lib/live/playback";
import { cn } from "@/lib/utils";

// Lines kept on screen; the screen reader hears them as they come (nextSaying, lib/live/described.ts),
// and the list is for reading back.
const SHOWN_LINES = 40;

/** What is said, with a graphic's Spanish or French wording marked so the screen reader says it in
 * that language's voice. The page is in English. */
function Spoken({ parts }: { parts: Part[] }) {
  return (
    <>
      {parts.map((part, i) => (
        <Fragment key={i}>
          {i > 0 && " "}
          {part.lang === "en" ? part.text : <span lang={part.lang}>{part.text}</span>}
        </Fragment>
      ))}
    </>
  );
}

/**
 * The described feed (docs/experience.md): the match in words as the viewer's playback reaches it,
 * spoken by the device's screen reader through a live region at the pace the listener chose. The list
 * on screen isn't the live region, so a backlog after a pause or at a fast replay is said once, as a
 * catch-up, rather than line by line.
 */
export function DescribedFeed({
  match,
  roster,
  base,
  startReplay,
  events,
  reached,
  cards,
  detail,
  pace,
  onDetail,
  onPace,
}: {
  match: MatchMeta;
  roster: Roster;
  base: StateView;
  startReplay: number;
  events: EventMessage[]; // every event since the replay's start
  reached: number; // how many of them the viewer's playback has reached
  cards: Shown[]; // the graphics airing for the viewer
  detail: Detail;
  pace: Pace;
  onDetail: (detail: Detail) => void;
  onPace: (pace: Pace) => void;
}) {
  const told = useMemo(
    () => eventLines(match, roster, base, startReplay, events.slice(0, reached)),
    [match, roster, base, startReplay, events, reached],
  );
  const all = merged(told, cardLines(cards)); // at every detail
  const lines = all.filter((l) => atDetail(l, detail));
  const [paused, setPaused] = useState(false);
  // `echo` alternates a trailing space, so an announcement worded like the one before still changes
  // the live region, and is spoken.
  const [saying, setSaying] = useState<{ parts: Part[]; echo: boolean }>({ parts: [], echo: false });
  const latest = useRef(all);
  const sayingAt = useRef(detail); // the detail lines are said at
  const said = useRef<Set<string> | null>(null);
  const resumed = useRef(false);

  useEffect(() => {
    latest.current = all;
  }, [all]);

  // What is there when the feed opens counts as said: the list shows it, and a listener wants what
  // happens next, not a reading of the match so far.
  useEffect(() => {
    said.current = new Set(latest.current.map((l) => l.key));
  }, []);

  // So do the lines a change of detail adds to what is there. Lines waiting to be said that the new
  // detail keeps still wait.
  useEffect(() => {
    const before = sayingAt.current;
    sayingAt.current = detail;
    const done = said.current;
    if (!done || before === detail) return;
    for (const l of latest.current) if (atDetail(l, detail) && !atDetail(l, before)) done.add(l.key);
  }, [detail]);

  useEffect(() => {
    if (paused) return;
    const speak = () => {
      const done = said.current;
      if (!done) return;
      const backlog = latest.current.filter((l) => atDetail(l, sayingAt.current) && !done.has(l.key));
      const parts = nextSaying(backlog, resumed.current);
      resumed.current = false;
      if (parts === null) return;
      for (const l of backlog) done.add(l.key);
      setSaying((s) => ({ parts, echo: !s.echo }));
    };
    speak();
    const timer = setInterval(speak, PACES[pace].seconds * 1000);
    return () => clearInterval(timer);
  }, [paused, pace]);

  function toggle() {
    if (paused) resumed.current = true;
    setPaused(!paused);
  }

  return (
    <section aria-labelledby="feed-title" className="overflow-hidden rounded-xl bg-card ring-1 ring-border">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b px-5 py-4">
        <div>
          <h2 id="feed-title" className="text-xl font-bold tracking-tight font-stretch-75%">
            Described feed
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">Read out by your screen reader as your stream reaches each moment.</p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="feed-detail">Detail</Label>
            <NativeSelect id="feed-detail" value={detail} onChange={(e) => onDetail(e.target.value as Detail)} className="h-9">
              {Object.entries(DETAILS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </NativeSelect>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="feed-pace">Pace</Label>
            <NativeSelect id="feed-pace" value={pace} onChange={(e) => onPace(e.target.value as Pace)} className="h-9">
              {Object.entries(PACES).map(([value, p]) => (
                <option key={value} value={value}>
                  {p.label}
                </option>
              ))}
            </NativeSelect>
          </div>
          {/* The label says what the button does now; a pressed state as well would be read as "Resume, pressed". */}
          <Button variant={paused ? "default" : "outline"} className="h-9" onClick={toggle}>
            {paused ? <Play aria-hidden /> : <Pause aria-hidden />} {paused ? "Resume" : "Pause"}
          </Button>
        </div>
      </div>
      <div aria-live="polite" aria-atomic="true" className="sr-only">
        <Spoken parts={saying.parts} />
        {saying.echo && NBSP}
      </div>
      {paused && (
        <p className="border-b bg-secondary/60 px-5 py-2 text-xs text-muted-foreground">
          Paused: new lines wait, and you hear what you missed when you resume.
        </p>
      )}
      {/* Focusable, so the list scrolls from the keyboard too. */}
      <ol
        tabIndex={0}
        aria-label="The match so far, latest first"
        className="max-h-112 space-y-1 overflow-y-auto px-5 py-4 text-[15px] outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:ring-inset"
      >
        {lines
          .slice(-SHOWN_LINES)
          .reverse()
          .map((line) => {
            const graphic = line.key.startsWith("card-");
            return (
              <li key={line.key} className={cn("grid grid-cols-[3.25rem_minmax(0,1fr)] gap-3 py-0.5", graphic && "my-1.5")}>
                <span className="pt-px text-sm text-muted-foreground figures">{line.clock}</span>
                <span
                  className={cn(
                    line.level === "key" && "font-semibold",
                    graphic && "chamfer-sm bg-secondary px-3 py-2 font-normal",
                  )}
                >
                  <Spoken parts={line.parts} />
                </span>
              </li>
            );
          })}
      </ol>
    </section>
  );
}
