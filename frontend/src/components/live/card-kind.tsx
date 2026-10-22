import {
  Activity,
  CircleDot,
  Crosshair,
  Footprints,
  Gauge,
  History,
  MonitorPlay,
  PenLine,
  RectangleVertical,
  Route,
  ScrollText,
  Zap,
} from "lucide-react";

import type { Club, Insight, InsightKind } from "@/lib/live/contract";
import { cn } from "@/lib/utils";

// What kind of moment a card is, at a glance: an icon for its topic, in the colour its kind carries
// (app/globals.css): goals and penalties in chalk, VAR in var, the provider's corrections in amend, a
// red card in tally, the rest quiet. The headline says the same in words.

type Tone = "score" | "var" | "amend" | "tally" | "recap" | "plain";

const TOPICS: Record<string, { icon: typeof Activity; tone: Tone }> = {
  goal: { icon: CircleDot, tone: "score" },
  own_goal: { icon: CircleDot, tone: "score" },
  penalty: { icon: Crosshair, tone: "score" },
  red_card: { icon: RectangleVertical, tone: "tally" },
  var_started: { icon: MonitorPlay, tone: "var" },
  var_decision: { icon: MonitorPlay, tone: "var" },
  key_pass: { icon: Route, tone: "plain" },
  hard_pass: { icon: Route, tone: "plain" },
  shot_speed: { icon: Gauge, tone: "plain" },
  sprint: { icon: Zap, tone: "plain" },
  distance: { icon: Footprints, tone: "plain" },
  half_time: { icon: ScrollText, tone: "recap" },
  full_time: { icon: ScrollText, tone: "recap" },
  catch_up: { icon: History, tone: "recap" },
  correction: { icon: PenLine, tone: "amend" },
};

const KINDS: Record<InsightKind, { icon: typeof Activity; tone: Tone }> = {
  moment: { icon: CircleDot, tone: "score" },
  rule_call: { icon: MonitorPlay, tone: "var" },
  segment: { icon: Activity, tone: "plain" },
  stat: { icon: Gauge, tone: "plain" },
  player_tag: { icon: Zap, tone: "plain" },
  recap: { icon: ScrollText, tone: "recap" },
  correction: { icon: PenLine, tone: "amend" },
};

const DISC: Record<Tone, string> = {
  score: "bg-foreground text-background",
  var: "bg-var/15 text-var ring-1 ring-var/40 ring-inset",
  amend: "bg-amend/15 text-amend ring-1 ring-amend/40 ring-inset",
  tally: "bg-tally/15 text-tally ring-1 ring-tally/40 ring-inset",
  recap: "bg-secondary text-foreground ring-1 ring-edge ring-inset",
  plain: "bg-secondary text-muted-foreground",
};

/** The colour a graphic of this kind is edged with on air, where the card isn't about one club. */
export const EDGE: Record<Tone, string> = {
  score: "var(--foreground)",
  var: "var(--var)",
  amend: "var(--amend)",
  tally: "var(--tally)",
  recap: "var(--foreground)",
  plain: "var(--muted-foreground)",
};

export function kindOf(insight: Insight): { icon: typeof Activity; tone: Tone } {
  return TOPICS[insight.topic] ?? KINDS[insight.kind];
}

/** The card's kind as an icon in a disc. */
export function KindIcon({ insight, className }: { insight: Insight; className?: string }) {
  const { icon: Icon, tone } = kindOf(insight);
  return (
    <span aria-hidden className={cn("grid size-7 shrink-0 place-items-center rounded-full", DISC[tone], className)}>
      <Icon className="size-3.5" />
    </span>
  );
}

/** The club a card is about, from its facts: the scorer's side, the side in control. */
export function clubOf(insight: Insight, home: Club, away: Club): Club | null {
  const named = insight.fields["moment.club"] ?? insight.fields["segment.club"];
  return named === home.short_name ? home : named === away.short_name ? away : null;
}
