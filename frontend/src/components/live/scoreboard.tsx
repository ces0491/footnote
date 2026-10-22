import { ClubKit } from "@/components/club-kit";
import { clubColour } from "@/lib/club-colour";
import type { Club, Phase, Score } from "@/lib/live/contract";
import { cn } from "@/lib/utils";

const PHASE: Record<Phase, string> = {
  pre_match: "Before kick-off",
  first_half: "First half",
  half_time: "Half-time",
  second_half: "Second half",
  full_time: "Full time",
};

// On a phone each side stands its kit over its short name, so neither name is cut short.
function Side({ club, align }: { club: Club; align: "start" | "end" }) {
  return (
    <div
      className={cn(
        "flex min-w-0 flex-col items-center gap-1.5 text-center sm:flex-row sm:gap-3 sm:text-left",
        align === "end" && "sm:flex-row-reverse sm:text-right",
      )}
    >
      <ClubKit club={club} className="size-9 sm:size-11" />
      <div className="max-w-full min-w-0">
        <div className="truncate text-base leading-tight font-bold tracking-tight font-stretch-75% sm:text-3xl">
          <span className="sm:hidden">{club.short_name}</span>
          <span className="hidden sm:inline">{club.name}</span>
        </div>
        <div className="hidden text-xs text-muted-foreground sm:block">{club.code}</div>
      </div>
    </div>
  );
}

/** The score as a broadcast's strip shows it, each side edged in its colour. */
export function Scoreboard({
  home,
  away,
  score,
  phase,
  clock,
}: {
  home: Club;
  away: Club;
  score: Score;
  phase: Phase;
  clock: string;
}) {
  return (
    <section aria-label="Score" className="chamfer relative bg-card">
      <span aria-hidden className="absolute inset-y-0 left-0 w-1.5" style={{ background: clubColour(home) }} />
      <span aria-hidden className="absolute inset-y-0 right-0 w-1.5" style={{ background: clubColour(away) }} />
      <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-3 px-5 py-4 sm:gap-8 sm:px-8 sm:py-5">
        <Side club={home} align="start" />
        <div className="text-center">
          <div className="text-5xl leading-none font-bold figures sm:text-6xl">
            {score.home}
            <span className="px-1.5 text-muted-foreground sm:px-2.5">–</span>
            {score.away}
          </div>
          <div className="mt-2 flex items-center justify-center gap-2 text-sm">
            <span className="rounded-sm bg-secondary px-2 py-0.5 font-semibold figures">{clock}</span>
            <span className="text-muted-foreground">{PHASE[phase]}</span>
          </div>
        </div>
        <Side club={away} align="end" />
      </div>
    </section>
  );
}
