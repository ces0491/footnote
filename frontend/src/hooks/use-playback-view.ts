"use client";

import { useMemo } from "react";

import type { EventMessage, StateView } from "@/lib/live/contract";
import { viewAfter } from "@/lib/live/playback";

/** The match after the first `count` events, folded again only when playback reaches another event. */
export function usePlaybackView(
  base: StateView | null,
  events: EventMessage[],
  live: StateView | null,
  count: number,
): StateView | null {
  return useMemo(() => viewAfter(base, events, live, count), [base, events, live, count]);
}
