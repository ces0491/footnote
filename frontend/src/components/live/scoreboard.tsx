import type { Club, Phase, Score } from "@/lib/live/contract";

const PHASE: Record<Phase, string> = {
  pre_match: "Before kick-off",
  first_half: "First half",
  half_time: "Half-time",
  second_half: "Second half",
  full_time: "Full time",
};

function Side({ club, align }: { club: Club; align: "start" | "end" }) {
  return (
    <div className={`flex min-w-0 items-center gap-3 ${align === "end" ? "flex-row-reverse text-right" : ""}`}>
      <span
        aria-hidden
        className="h-10 w-2 shrink-0 rounded-full"
        style={{ background: `linear-gradient(${club.colours[0]} 60%, ${club.colours[1]} 60%)` }}
      />
      <div className="min-w-0">
        <div className="truncate text-lg font-semibold sm:text-xl">
          <span className="sm:hidden">{club.short_name}</span>
          <span className="hidden sm:inline">{club.name}</span>
        </div>
        <div className="text-xs uppercase tracking-wide text-zinc-400">{club.code}</div>
      </div>
    </div>
  );
}

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
    <section aria-label="Score" className="rounded-xl bg-zinc-950 px-4 py-4 text-zinc-50 sm:px-6">
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 sm:gap-6">
        <Side club={home} align="start" />
        <div className="text-center font-mono text-4xl font-bold tabular-nums sm:text-5xl">
          {score.home}
          <span className="px-2 text-zinc-500">–</span>
          {score.away}
        </div>
        <Side club={away} align="end" />
      </div>
      <div className="mt-3 flex items-center justify-center gap-3 text-sm text-zinc-300">
        <span className="font-mono tabular-nums">{clock}</span>
        <span aria-hidden className="text-zinc-600">·</span>
        <span>{PHASE[phase]}</span>
      </div>
    </section>
  );
}
