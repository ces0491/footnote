import { connection } from "next/server";
import { Suspense } from "react";

import { Wordmark } from "@/components/brand";
import { ClubKit } from "@/components/club-kit";
import { StartReplay } from "@/components/start-replay";
import { Skeleton } from "@/components/ui/skeleton";
import { clubColour } from "@/lib/club-colour";
import type { Club, MatchMeta } from "@/lib/live/contract";
import { db } from "@/lib/server/db";

function Side({ club }: { club: Club }) {
  return (
    <div className="flex items-center gap-4 border-l-4 py-1 pl-4" style={{ borderLeftColor: clubColour(club) }}>
      <ClubKit club={club} className="size-11" />
      <div className="min-w-0 truncate text-3xl leading-none font-bold tracking-tight font-stretch-75% sm:text-4xl">{club.name}</div>
    </div>
  );
}

/** The fixture on offer, billed as a broadcast would bill it. */
async function Fixture() {
  await connection();
  let match: MatchMeta | undefined;
  try {
    const { rows } = await db().query("select meta from matches order by updated_at desc limit 1");
    match = rows[0]?.meta;
  } catch (error) {
    console.error("loading the match failed", error);
  }
  if (!match) return <h2 className="text-2xl font-bold font-stretch-75%">The showcase match</h2>;
  return (
    <>
      <div className="flex flex-wrap justify-between gap-x-4 gap-y-1 text-sm text-muted-foreground">
        <span>
          {match.competition} {match.season}
        </span>
        <span>{match.venue}</span>
      </div>
      <h2 className="sr-only">
        {match.home.name} v {match.away.name}
      </h2>
      <div aria-hidden className="mt-6 space-y-2">
        <Side club={match.home} />
        <div className="pl-5 text-sm font-semibold text-muted-foreground">v</div>
        <Side club={match.away} />
      </div>
      <p className="mt-6 text-sm text-muted-foreground">Referee {match.referee.name}</p>
    </>
  );
}

// How a card gets made, in order (README, "Status").
const STEPS = [
  {
    title: "Ranked",
    text: "The processor finds the moments worth a card, ranks them with a match-state model and words each with a template.",
  },
  {
    title: "Redrafted",
    text: "Writers built with Microsoft Agent Framework on a Foundry model redraft the cards where wording adds something, reading the match only through our MCP match tools.",
  },
  {
    title: "Checked",
    text: "No writer types a figure: code fills each one in and checks every draft. A draft that fails or comes late leaves the template on screen.",
  },
  {
    title: "Delivered",
    text: "An approved card reaches each viewer when their own stream reaches the moment, in English, or in Spanish or French through Azure AI Translator.",
  },
];

export default function Home() {
  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-4 sm:px-6">
      <header className="py-5">
        <Wordmark className="text-2xl" />
      </header>
      <section className="grid gap-10 pt-6 pb-14 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:items-center lg:pt-14">
        <div>
          <h1 className="max-w-[12ch] text-5xl leading-[0.92] font-bold tracking-tight text-balance font-stretch-75% sm:text-7xl">
            Explained match intelligence
          </h1>
          <p className="mt-6 max-w-xl text-lg text-muted-foreground">
            Moments ranked by a match-state model, phrased for each viewer, linked to the events behind them, and delivered when each
            viewer&apos;s stream reaches them.
          </p>
          <p className="mt-3 max-w-xl text-muted-foreground">
            Watch the showcase match as Nadia, the producer who approves each graphic before it airs, or as one of four fans.
          </p>
        </div>
        <div className="chamfer bg-card p-6 sm:p-8">
          <Suspense fallback={<Skeleton className="h-56 w-full" />}>
            <Fixture />
          </Suspense>
        </div>
      </section>
      <StartReplay />
      <section aria-labelledby="how-title" className="mt-16 border-t py-12">
        <h2 id="how-title" className="text-3xl font-bold tracking-tight font-stretch-75%">
          How a card is made
        </h2>
        <ol className="mt-6 grid gap-x-6 gap-y-8 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((step, i) => (
            <li key={step.title} className="border-t-2 border-edge pt-4">
              <h3 className="flex items-baseline gap-2 text-lg font-semibold">
                <span className="text-muted-foreground figures">{i + 1}</span>
                {step.title}
              </h3>
              <p className="mt-2 text-sm text-muted-foreground">{step.text}</p>
            </li>
          ))}
        </ol>
        <p className="mt-10 max-w-3xl text-sm text-muted-foreground">
          It runs on Microsoft Azure: Event Hubs carries the feed, Container Apps runs the services, Azure Database for PostgreSQL keeps
          each replay&apos;s state and cards, Web PubSub pushes them to the page, and Application Insights traces every draft.
        </p>
      </section>
      <footer className="border-t py-8 text-xs text-muted-foreground">
        Everything here is synthetic: the league, clubs, players, officials and matches are generated by code. No real match data,
        footage, clubs, players or crests are used.
      </footer>
    </main>
  );
}
