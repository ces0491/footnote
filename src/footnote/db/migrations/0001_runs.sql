-- Matches, replays of them, the feed each replay played, and the state view viewers read.

-- Match metadata (clubs, line-ups, referee) as the provider publishes it before kick-off. The
-- processor writes it from the committed match files when it starts.
create table matches (
    match_id    text primary key,
    meta        jsonb not null,
    updated_at  timestamptz not null default now()
);

create table runs (
    run_id      text primary key,
    match_id    text not null references matches (match_id),
    descriptor  jsonb not null,
    status      text not null default 'running'
                check (status in ('running', 'finished', 'stopped', 'expired', 'evicted', 'failed')),
    created_at  timestamptz not null default now(),
    ended_at    timestamptz
);

-- Every feed message a run processed, as the provider published it. The source of truth for the
-- run's state: the processor rebuilds state from here after a restart.
create table feed_events (
    run_id        text not null references runs (run_id) on delete cascade,
    seq           integer not null,
    event_id      text not null,
    version       integer not null,
    type          text not null,
    period        smallint not null,
    clock         double precision not null,
    body          jsonb not null,
    published_at  timestamptz not null,
    enqueued_at   timestamptz,
    processed_at  timestamptz not null default now(),
    primary key (run_id, seq)
);

create index feed_events_by_event on feed_events (run_id, event_id, version);

-- The latest state view of each run, for viewers who join or fall behind.
create table run_state (
    run_id      text primary key references runs (run_id) on delete cascade,
    seq         integer not null,
    view        jsonb not null,
    updated_at  timestamptz not null default now()
);
