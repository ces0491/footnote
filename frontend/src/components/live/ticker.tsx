import { CircleDot, Flag, Footprints, Gauge, History, MonitorPlay, RectangleVertical, Timer } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { FeedEvent, Tag } from "@/lib/live/contract";
import { type EventTone, type Roster, tickerLines } from "@/lib/live/describe";
import { minuteLabel } from "@/lib/live/timeline";
import { cn } from "@/lib/utils";

const ICON: Record<EventTone, typeof CircleDot> = {
  goal: CircleDot,
  var: MonitorPlay,
  card: RectangleVertical,
  correction: History,
  period: Timer,
  plain: Flag,
  sprint: Gauge,
  distance: Footprints,
};

export function Ticker({ events, tags, roster }: { events: FeedEvent[]; tags: Tag[]; roster: Roster }) {
  const lines = tickerLines(events, tags, roster);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Key moments</CardTitle>
      </CardHeader>
      <CardContent>
        {lines.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing yet.</p>
        ) : (
          // Focusable, so the list scrolls from the keyboard too.
          <ol
            tabIndex={0}
            aria-label="Key moments, latest first"
            className="max-h-128 space-y-2 overflow-y-auto rounded-md pr-1 outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
          >
            {[...lines].reverse().map((line) => {
              const Icon = ICON[line.tone];
              return (
                <li
                  key={line.key}
                  className={cn(
                    "flex items-start gap-3 rounded-md px-2 py-1.5 text-sm",
                    line.tone === "goal" && "bg-emerald-50 font-medium dark:bg-emerald-950/40",
                    line.tone === "correction" && "bg-amber-50 dark:bg-amber-950/40",
                    (line.tone === "sprint" || line.tone === "distance") && "text-muted-foreground",
                  )}
                >
                  <Badge variant="outline" className="w-14 shrink-0 justify-center font-mono tabular-nums">
                    {minuteLabel(line.minute, line.addedMinute)}
                  </Badge>
                  <Icon aria-hidden className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                  <span>
                    {line.text}
                    {line.correctedAt && (
                      <span className="block text-xs font-medium text-amber-700 dark:text-amber-400">
                        Corrected by the data provider at {line.correctedAt}
                      </span>
                    )}
                  </span>
                </li>
              );
            })}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
