"use client";

import { Play } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { type RunDescriptor, SPEEDS } from "@/lib/live/contract";
import { PROFILES, type Profile, rememberStarted } from "@/lib/live/profiles";
import { viewerId } from "@/lib/live/viewer";
import { cn } from "@/lib/utils";

// The judges' jump points from docs/experience.md; each replay starts 30 s before its minute.
const JUMPS = [
  { minute: 1, label: "Kick-off" },
  { minute: 23, label: "23'" },
  { minute: 31, label: "31'" },
  { minute: 60, label: "60'" },
  { minute: 81, label: "81'" },
];

export function StartReplay() {
  const router = useRouter();
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
                "rounded-lg border p-3 text-left text-sm transition-colors outline-none hover:bg-muted focus-visible:ring-[3px] focus-visible:ring-ring/50",
                who === p.id && "border-foreground bg-muted",
              )}
            >
              <div className="font-medium">
                {p.name} <span className="font-normal text-muted-foreground">· {p.role === "producer" ? "producer" : "fan"}</span>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">{p.summary}</p>
            </button>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">You can switch between them during the replay.</p>
      </fieldset>
      <div className="space-y-2">
        <div className="text-sm font-medium" id="jump-label">
          Start from
        </div>
        <ToggleGroup type="single" variant="outline" value={minute} onValueChange={(v) => v && setMinute(v)} aria-labelledby="jump-label">
          {JUMPS.map((j) => (
            <ToggleGroupItem key={j.minute} value={String(j.minute)} className="px-3">
              {j.label}
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
      <Button onClick={start} disabled={starting}>
        <Play /> {starting ? "Starting…" : "Start the replay"}
      </Button>
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
    </div>
  );
}
