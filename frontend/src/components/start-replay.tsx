"use client";

import { Play } from "lucide-react";
import { useRouter } from "next/navigation";
import { type ReactNode, useState, useSyncExternalStore } from "react";

import { PersonaBadge, roleLabel } from "@/components/persona";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { type RunDescriptor, SPEEDS } from "@/lib/live/contract";
import { PROFILES, type Profile, profile, rememberStarted } from "@/lib/live/profiles";
import { viewerId } from "@/lib/live/viewer";

// Kick-off and the jump points of the judges' path (README.md, "Try it"), each with what happens
// there and the viewers who show it best. Each replay starts 30 s before its minute.
const JUMPS = [
  { minute: 1, label: "Kick-off", moment: "The whole match", who: null },
  { minute: 23, label: "23'", moment: "Kingsferry score", who: "Nadia, then Sam" },
  { minute: 31, label: "31'", moment: "A goal VAR rules out", who: "Tom's described feed" },
  { minute: 60, label: "60'", moment: "Join late", who: "Lucía, in Spanish" },
  { minute: 81, label: "81'", moment: "The amended goal", who: "Nadia's corrections" },
];

const never = () => () => {};

/** One of the choices before the replay starts, numbered: they are made in order. */
function Step({ n, id, title, children }: { n: number; id: string; title: string; children: ReactNode }) {
  return (
    <div className="space-y-4">
      <h2 id={id} className="flex items-center gap-3 text-2xl font-bold tracking-tight font-stretch-75%">
        <span aria-hidden className="grid size-7 place-items-center rounded-full bg-secondary text-sm font-semibold ring-1 ring-edge figures">
          {n}
        </span>
        {title}
      </h2>
      {children}
    </div>
  );
}

export function StartReplay() {
  const router = useRouter();
  // False on the server and until the page has hydrated: a click before then would be lost.
  const ready = useSyncExternalStore(never, () => true, () => false);
  const [who, setWho] = useState<Profile["id"]>("sam");
  const [minute, setMinute] = useState("23");
  const [speed, setSpeed] = useState("2");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const jump = JUMPS.find((j) => String(j.minute) === minute) ?? JUMPS[1];

  async function start() {
    setStarting(true);
    setError(null);
    try {
      // Picking the producer means approving each graphic by hand; a fan's replay approves them as
      // they're found. Either can be switched in the producer console.
      const producer = PROFILES.find((p) => p.id === who)?.role === "producer" ? "manual" : "auto";
      const response = await fetch("/api/runs", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ start_minute: Number(minute), speed: Number(speed), viewer: viewerId(), producer }),
      });
      const body = (await response.json()) as RunDescriptor | { error: string };
      if (!response.ok || "error" in body) throw new Error("error" in body ? body.error : `HTTP ${response.status}`);
      rememberStarted(body.run_id);
      router.push(`/runs/${body.run_id}?as=${who}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setStarting(false);
    }
  }

  return (
    <section aria-label="Start a replay" className="space-y-12">
      <Step n={1} id="who-label" title="Watch as">
        <ToggleGroup
          type="single"
          value={who}
          onValueChange={(v) => v && setWho(v as Profile["id"])}
          aria-labelledby="who-label"
          className="grid w-full items-stretch gap-3 sm:grid-cols-2 lg:grid-cols-5"
        >
          {PROFILES.map((p) => (
            <ToggleGroupItem
              key={p.id}
              value={p.id}
              className="group/who h-full flex-col items-stretch justify-start gap-3 rounded-xl border border-border bg-card p-4 text-left font-normal whitespace-normal hover:bg-secondary data-[state=on]:border-foreground data-[state=on]:bg-secondary"
            >
              <span className="flex items-center gap-3">
                <PersonaBadge id={p.id} className="group-data-[state=on]/who:bg-foreground group-data-[state=on]/who:text-background" />
                <span className="leading-tight">
                  <span className="block text-base font-semibold">{p.name}</span>
                  <span className="block text-xs text-muted-foreground">{roleLabel(p)}</span>
                </span>
              </span>
              <span className="text-sm text-muted-foreground">{p.summary}</span>
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </Step>
      <div className="grid gap-12 lg:grid-cols-[minmax(0,1fr)_auto]">
        <Step n={2} id="jump-label" title="Start from">
          <ToggleGroup
            type="single"
            value={minute}
            onValueChange={(v) => v && setMinute(v)}
            aria-labelledby="jump-label"
            className="relative grid w-full items-stretch gap-1 sm:grid-cols-5 sm:gap-3"
          >
            {/* The match's timeline through the markers: down the side on a phone, across on a wider screen. */}
            <span
              aria-hidden
              className="pointer-events-none absolute top-6 bottom-6 left-4.75 w-px bg-edge sm:top-5.75 sm:right-[calc((100%-3rem)/10)] sm:bottom-auto sm:left-[calc((100%-3rem)/10)] sm:h-px sm:w-auto"
            />
            {JUMPS.map((j) => (
              <ToggleGroupItem
                key={j.minute}
                value={String(j.minute)}
                aria-label={[j.label, j.moment, j.who].filter(Boolean).join(", ")}
                className="group/jump h-auto items-start justify-start gap-3 rounded-xl p-3 text-left font-normal whitespace-normal hover:bg-secondary data-[state=on]:bg-secondary sm:flex-col sm:items-center sm:text-center"
              >
                <span
                  aria-hidden
                  className="relative mt-1 size-3.5 shrink-0 rounded-full border-2 border-edge bg-background group-data-[state=on]/jump:border-foreground group-data-[state=on]/jump:bg-foreground sm:mt-1"
                />
                <span className="space-y-1">
                  <span className="block text-2xl leading-none font-bold figures">{j.label}</span>
                  <span className="block text-sm">{j.moment}</span>
                  {j.who && <span className="block text-xs text-muted-foreground">{j.who}</span>}
                </span>
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </Step>
        <Step n={3} id="speed-label" title="Speed">
          <ToggleGroup type="single" variant="outline" spacing={0} value={speed} onValueChange={(v) => v && setSpeed(v)} aria-labelledby="speed-label">
            {SPEEDS.map((s) => (
              <ToggleGroupItem key={s} value={String(s)} className="h-11 min-w-16 px-4 text-lg font-semibold figures data-[state=on]:bg-foreground data-[state=on]:text-background">
                {s}×
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </Step>
      </div>
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-t pt-8">
        <Button size="lg" className="h-12 px-6 text-base" onClick={start} disabled={!ready || starting}>
          <Play /> {!ready ? "Loading…" : starting ? "Starting…" : "Start the replay"}
        </Button>
        <p className="text-sm text-muted-foreground">
          As {profile(who).name}, from {jump.minute === 1 ? "kick-off" : jump.label}, at {speed}×. You can switch between viewers during the
          replay.
        </p>
      </div>
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
    </section>
  );
}
