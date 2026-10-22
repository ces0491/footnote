import { CircleDot, Flag, Footprints, Gauge, MonitorPlay, PenLine, RectangleVertical, Timer } from "lucide-react";

import type { FeedEvent, Tag } from "@/lib/live/contract";
import { type EventTone, type Roster, type TickerLine, tickerLines } from "@/lib/live/describe";
import { minuteLabel } from "@/lib/live/timeline";
import { cn } from "@/lib/utils";

const ICON: Record<EventTone, typeof CircleDot> = {
  goal: CircleDot,
  var: MonitorPlay,
  card: RectangleVertical,
  correction: PenLine,
  period: Timer,
  plain: Flag,
  sprint: Gauge,
  distance: Footprints,
};

/** The disc a line's icon sits in: a goal stands out, VAR and corrections in their colours, a card in its own. */
function disc(line: TickerLine): string {
  switch (line.tone) {
    case "goal":
      return line.ruledOutAt ? "bg-secondary text-muted-foreground" : "bg-foreground text-background";
    case "var":
      return "bg-var/15 text-var";
    case "correction":
      return "bg-amend/15 text-amend";
    case "card":
      return /^(Red|Second yellow)/.test(line.text) ? "bg-tally/15 text-tally [&_svg]:fill-current" : "bg-cite/15 text-cite [&_svg]:fill-current";
    case "period":
      return "bg-secondary text-foreground";
    default:
      return "bg-secondary text-muted-foreground";
  }
}

export function Ticker({ events, tags, roster }: { events: FeedEvent[]; tags: Tag[]; roster: Roster }) {
  const lines = tickerLines(events, tags, roster);
  return (
    <section aria-labelledby="moments-title" className="overflow-hidden rounded-xl bg-card ring-1 ring-border">
      <h2 id="moments-title" className="border-b px-5 py-4 text-xl font-bold tracking-tight font-stretch-75%">
        Key moments
      </h2>
      {lines.length === 0 ? (
        <p className="px-5 py-5 text-sm text-muted-foreground">Nothing yet.</p>
      ) : (
        // Focusable, so the list scrolls from the keyboard too.
        <ol
          tabIndex={0}
          aria-label="Key moments, latest first"
          className="max-h-128 overflow-y-auto px-5 py-3 outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:ring-inset"
        >
          {[...lines].reverse().map((line) => {
            const Icon = ICON[line.tone];
            return (
              <li
                key={line.key}
                className="relative grid grid-cols-[2.5rem_1.5rem_minmax(0,1fr)] items-start gap-x-3 py-1.5 before:absolute before:inset-y-0 before:left-[calc(4rem-0.5px)] before:w-px before:bg-border first:before:top-4.5 last:before:bottom-auto last:before:h-4.5 only:before:hidden"
              >
                <span className="pt-0.5 text-sm font-semibold text-muted-foreground figures">{minuteLabel(line.minute, line.addedMinute)}</span>
                {/* On the card's own colour, so the line through the icons stops at each one. */}
                <span aria-hidden className="relative rounded-full bg-card">
                  <span className={cn("grid size-6 place-items-center rounded-full", disc(line))}>
                    <Icon className="size-3.5" />
                  </span>
                </span>
                <span
                  className={cn(
                    "pt-0.5 text-sm",
                    line.tone === "goal" && !line.ruledOutAt && "font-semibold",
                    (line.tone === "sprint" || line.tone === "distance") && "text-muted-foreground",
                  )}
                >
                  {line.text}
                  {line.correctedAt && (
                    <span className="block text-xs font-medium text-amend">Corrected by the data provider at {line.correctedAt}</span>
                  )}
                  {line.ruledOutAt && <span className="block text-xs font-medium text-var">Ruled out by VAR at {line.ruledOutAt}</span>}
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
