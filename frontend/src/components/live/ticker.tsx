import { CircleDot, Flag, History, MonitorPlay, RectangleVertical, Timer } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { FeedEvent } from "@/lib/live/contract";
import { describe, type EventTone, type Roster } from "@/lib/live/describe";
import { minuteLabel } from "@/lib/live/timeline";
import { cn } from "@/lib/utils";

const ICON: Record<EventTone, typeof CircleDot> = {
  goal: CircleDot,
  var: MonitorPlay,
  card: RectangleVertical,
  correction: History,
  period: Timer,
  plain: Flag,
};

export function Ticker({ events, roster }: { events: FeedEvent[]; roster: Roster }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Key moments</CardTitle>
      </CardHeader>
      <CardContent>
        {events.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing yet.</p>
        ) : (
          <ol className="max-h-128 space-y-2 overflow-y-auto pr-1">
            {[...events].reverse().map((event) => {
              const line = describe(event, roster);
              const Icon = ICON[line.tone];
              return (
                <li
                  key={`${event.seq}`}
                  className={cn(
                    "flex items-start gap-3 rounded-md px-2 py-1.5 text-sm",
                    line.tone === "goal" && "bg-emerald-50 font-medium dark:bg-emerald-950/40",
                    line.tone === "correction" && "bg-amber-50 dark:bg-amber-950/40",
                  )}
                >
                  <Badge variant="outline" className="w-14 shrink-0 justify-center font-mono tabular-nums">
                    {minuteLabel(event.minute, event.added_minute)}
                  </Badge>
                  <Icon aria-hidden className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                  <span>{line.text}</span>
                </li>
              );
            })}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
