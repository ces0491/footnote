"use client";

import { Play } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, useSyncExternalStore } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { type RunDescriptor, SPEEDS } from "@/lib/live/contract";
import { PROFILES, type Profile, rememberStarted } from "@/lib/live/profiles";
import { viewerId } from "@/lib/live/viewer";
import { cn } from "@/lib/utils";

// The judges' jump points from docs/experience.md, each with what happens there and the viewers who
// show it best. Each replay starts 30 s before its minute.
const JUMPS = [
  { minute: 1, label: "Kick-off", moment: "The whole match", who: null },
  { minute: 23, label: "23'", moment: "Kingsferry score", who: "Nadia, then Sam" },
  { minute: 31, label: "31'", moment: "A goal VAR rules out", who: "Tom's described feed" },
  { minute: 60, label: "60'", moment: "Join late", who: "Lucía, in Spanish" },
  { minute: 81, label: "81'", moment: "The amended goal", who: "Nadia's corrections" },
];

// Muted text on a selected or hovered choice sits on the muted background, where the muted colour
// falls short of 4.5:1 contrast; a darker one keeps it readable.
const MUTED_ON_TOGGLE = "text-muted-foreground group-hover/toggle:text-foreground/70 group-data-[state=on]/toggle:text-foreground/70";
const MUTED_ON_CARD = "text-muted-foreground group-hover:text-foreground/70 group-aria-checked:text-foreground/70";

const never = () => () => {};

export function StartReplay() {
  const router = useRouter();
  // False on the server and until the page has hydrated: a click before then would be lost.
  const ready = useSyncExternalStore(never, () => true, () => false);
  const [who, setWho] = useState<Profile["id"]>("sam");
  const [minute, setMinute] = useState("23");
  const [speed, setSpeed] = useState("2");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    <div className="space-y-5">
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Watch as</legend>
        <div className="grid gap-2 sm:grid-cols-2" role="radiogroup" aria-label="Watch as">
          {PROFILES.map((p) => (
            <button
              key={p.id}
              type="button"
              role="radio"
              aria-checked={who === p.id}
              onClick={() => setWho(p.id)}
              className={cn(
                "group rounded-lg border p-3 text-left text-sm transition-colors outline-none hover:bg-muted focus-visible:ring-[3px] focus-visible:ring-ring/50",
                who === p.id && "border-foreground bg-muted",
              )}
            >
              <div className="font-medium">
                {p.name} <span className={cn("font-normal", MUTED_ON_CARD)}>· {p.role === "producer" ? "producer" : "fan"}</span>
              </div>
              <p className={cn("mt-1 text-xs", MUTED_ON_CARD)}>{p.summary}</p>
            </button>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">You can switch between them during the replay.</p>
      </fieldset>
      <div className="space-y-2">
        <div className="text-sm font-medium" id="jump-label">
          Start from
        </div>
        <ToggleGroup
          type="single"
          variant="outline"
          value={minute}
          onValueChange={(v) => v && setMinute(v)}
          aria-labelledby="jump-label"
          className="grid w-full grid-cols-2 items-stretch sm:grid-cols-5"
        >
          {JUMPS.map((j) => (
            <ToggleGroupItem
              key={j.minute}
              value={String(j.minute)}
              aria-label={[j.label, j.moment, j.who].filter(Boolean).join(", ")}
              className="h-auto flex-col items-start justify-start gap-0.5 px-3 py-2 text-left whitespace-normal"
            >
              <span>{j.label}</span>
              <span className="text-xs font-normal">{j.moment}</span>
              {j.who && <span className={cn("text-xs font-normal", MUTED_ON_TOGGLE)}>{j.who}</span>}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>
      <div className="space-y-2">
        <div className="text-sm font-medium" id="speed-label">
          Speed
        </div>
        <ToggleGroup type="single" variant="outline" value={speed} onValueChange={(v) => v && setSpeed(v)} aria-labelledby="speed-label">
          {SPEEDS.map((s) => (
            <ToggleGroupItem key={s} value={String(s)} className="px-3">
              {s}×
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>
      <Button onClick={start} disabled={!ready || starting}>
        <Play /> {!ready ? "Loading…" : starting ? "Starting…" : "Start the replay"}
      </Button>
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
    </div>
  );
}
