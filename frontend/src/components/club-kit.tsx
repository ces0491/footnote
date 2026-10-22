import type { Club } from "@/lib/live/contract";
import { cn } from "@/lib/utils";

/**
 * A club's shirt in its kit colours: how fans know a side, and no crest (the league is fictional
 * and has none). Outlined in the second colour, so a dark kit still shows on the dark page.
 */
export function ClubKit({ club, className }: { club: Club; className?: string }) {
  const [body, trim] = club.colours;
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cn("size-8 shrink-0", className)} strokeLinejoin="round" strokeLinecap="round">
      <path
        d="M11 3.5 6 5.5 1.8 11.6l4.6 3.1L8.5 12V28h15V12l2.1 2.7 4.6-3.1L26 5.5l-5-2c-.8 2.4-2.6 3.8-5 3.8s-4.2-1.4-5-3.8Z"
        fill={body}
        stroke={trim}
        strokeWidth={1.4}
      />
      <path d="M11 3.5c.8 2.4 2.6 3.8 5 3.8s4.2-1.4 5-3.8" fill="none" stroke={trim} strokeWidth={2} />
      <path d="M2.4 12l4 2.7M29.6 12l-4 2.7" fill="none" stroke={trim} strokeWidth={2.4} />
    </svg>
  );
}
