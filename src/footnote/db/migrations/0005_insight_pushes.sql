-- Every insight change a run's viewers were pushed, by the revision it took, as each writer sent it
-- (the processor, the agents and the producer's desk). A page that loads after a card changed can
-- then show the card as it stood at its viewer's playback, not only as it stands now: a goal VAR
-- later rules out stays a goal on a delayed screen until that screen reaches the decision
-- (docs/overlay.md). Changes to insights the backfill passed aren't pushed, so their revisions
-- aren't here: viewers get those insights through the snapshot.
create table insight_pushes (
    run_id  text not null references runs (run_id) on delete cascade,
    rev     integer not null,
    push    jsonb not null,  -- the insight message, timing aside
    primary key (run_id, rev)
);
