"use client";

import { Play } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { type RunDescriptor, SPEEDS } from "@/lib/live/contract";

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
  const [minute, setMinute] = useState("1");
  const [speed, setSpeed] = useState("1");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setStarting(true);
    setError(null);
    try {
      const response = await fetch("/api/runs", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ start_minute: Number(minute), speed: Number(speed) }),
      });
      const body = (await response.json()) as RunDescriptor | { error: string };
      if (!response.ok || "error" in body) throw new Error("error" in body ? body.error : `HTTP ${response.status}`);
      router.push(`/runs/${body.run_id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setStarting(false);
    }
  }

  return (
    <div className="space-y-5">
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
