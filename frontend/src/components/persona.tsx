import { AudioLines, ChartLine, Headset, Languages, Tv } from "lucide-react";

import type { Profile } from "@/lib/live/profiles";
import { cn } from "@/lib/utils";

// What each ready-made viewer shows (docs/experience.md, "The people"): Nadia produces, Sam watches
// casually, Priya reads the figures, Lucía reads Spanish, Tom listens.
const ICON: Record<Profile["id"], typeof Tv> = {
  nadia: Headset,
  sam: Tv,
  priya: ChartLine,
  lucia: Languages,
  tom: AudioLines,
};

/** A viewer's badge: the icon of what they show, in a ring. */
export function PersonaBadge({ id, className }: { id: Profile["id"]; className?: string }) {
  const Icon = ICON[id];
  return (
    <span aria-hidden className={cn("grid size-8 shrink-0 place-items-center rounded-full bg-secondary ring-1 ring-edge", className)}>
      <Icon className="size-4" />
    </span>
  );
}

export function roleLabel(p: Profile): string {
  return p.role === "producer" ? "Producer" : "Fan";
}
