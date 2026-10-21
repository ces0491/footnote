"use client";

import { Pause, Play } from "lucide-react";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import type { EventMessage, MatchMeta, StateView } from "@/lib/live/contract";
import { NBSP, type Roster } from "@/lib/live/describe";
import { atDetail, cardLines, type Detail, DETAILS, eventLines, merged, nextSaying, type Pace, PACES, type Part } from "@/lib/live/described";
import type { Shown } from "@/lib/live/playback";

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
    <Card>
      <CardHeader className="space-y-3">
        <CardTitle>
          <h2>Described feed</h2>
        </CardTitle>
        <div className="flex flex-wrap items-end gap-3">
          <div className="grid gap-1">
            <Label htmlFor="feed-detail">Detail</Label>
            <NativeSelect id="feed-detail" value={detail} onChange={(e) => onDetail(e.target.value as Detail)}>
              {Object.entries(DETAILS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </NativeSelect>
          </div>
          <div className="grid gap-1">
            <Label htmlFor="feed-pace">Pace</Label>
            <NativeSelect id="feed-pace" value={pace} onChange={(e) => onPace(e.target.value as Pace)}>
              {Object.entries(PACES).map(([value, p]) => (
                <option key={value} value={value}>
                  {p.label}
                </option>
              ))}
            </NativeSelect>
          </div>
          {/* The label says what the button does now; a pressed state as well would be read as "Resume, pressed". */}
          <Button variant="outline" onClick={toggle}>
            {paused ? <Play aria-hidden /> : <Pause aria-hidden />} {paused ? "Resume" : "Pause"}
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <div aria-live="polite" aria-atomic="true" className="sr-only">
          <Spoken parts={saying.parts} />
          {saying.echo && NBSP}
        </div>
        {/* Focusable, so the list scrolls from the keyboard too. */}
        <ol
          tabIndex={0}
          aria-label="The match so far, latest first"
          className="max-h-96 space-y-1.5 overflow-y-auto rounded-md pr-1 text-sm outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
        >
          {lines
            .slice(-SHOWN_LINES)
            .reverse()
            .map((line) => (
              <li key={line.key} className="flex gap-3">
                <span className="w-12 shrink-0 font-mono text-xs leading-5 tabular-nums text-muted-foreground">{line.clock}</span>
                <span className={line.level === "key" ? "font-medium" : undefined}>
                  <Spoken parts={line.parts} />
                </span>
              </li>
            ))}
        </ol>
        {paused && <p className="mt-2 text-xs text-muted-foreground">Paused: new lines wait, and you hear what you missed when you resume.</p>}
      </CardContent>
    </Card>
  );
}
