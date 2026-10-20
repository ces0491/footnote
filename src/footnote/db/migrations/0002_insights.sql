-- Insights: the moments worth a card in each run, every version of their wording, and the agents'
-- work on them (src/footnote/insights, src/footnote/agents).

-- Bumped with every change to one of the run's insights. Each pushed insight carries the revision
-- it made, so a viewer who misses one sees the gap and fetches the snapshot again.
alter table runs add column insight_rev integer not null default 0;

create table insights (
    run_id          text not null references runs (run_id) on delete cascade,
    insight_id      text not null,
    seq             integer not null,       -- the feed seq its facts are as of
    kind            text not null,
    topic           text not null,
    at              jsonb not null,         -- period, t, minute, added_minute: when it happened
    until_at        jsonb not null,         -- period, t: when it leaves the shortlist
    rank            real not null,
    reason          text not null,
    evidence        jsonb not null,         -- the IDs of the events it cites
    placement       text not null,
    hold            text,                   -- 'stoppage': shown at the next stoppage
    corrects        text,                   -- the insight a correction is about
    live            boolean not null,       -- false for moments the run's backfill passed
    flag            jsonb,                  -- set when VAR or a correction undoes what it cites
    facts           jsonb not null,
    facts_version   integer not null,
    template        jsonb not null,         -- the code's own draft, with placeholders
    status          text not null default 'drafted'
                    check (status in ('drafted', 'approved', 'aired', 'withdrawn', 'killed')),
    status_by       text,
    status_at       timestamptz,
    agent_state     text not null check (agent_state in ('off', 'pending', 'drafting', 'done', 'fallback')),
    agent_note      text,                   -- why a draft fell back to the template
    agent_attempts  integer not null default 0,
    agent_lease     timestamptz,            -- a drafting claim expires, so a crashed worker's job is retried
    redraft         boolean not null default false,  -- a fresh agent draft was asked for, past the cache
    version         integer not null default 1,      -- the version viewers see
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    primary key (run_id, insight_id)
);

create index insights_agent_queue on insights (created_at) where agent_state in ('pending', 'drafting');

create table insight_versions (
    run_id          text not null,
    insight_id      text not null,
    version         integer not null,
    source          text not null check (source in ('template', 'agent')),
    facts_version   integer not null,
    draft           jsonb not null,         -- the wording, with placeholders
    card            jsonb not null,         -- filled in: headline, casual, analyst, plain, evidence, facts
    provenance      jsonb not null,         -- the template, or the agent run, model, checks and cache
    created_at      timestamptz not null default now(),
    primary key (run_id, insight_id, version),
    foreign key (run_id, insight_id) references insights (run_id, insight_id) on delete cascade
);

-- What viewers get for an insight: its current version, without the working fields. The processor
-- and the agents push rows of it; the web app serves them in the snapshot.
create view insight_cards as
select
    i.run_id,
    i.insight_id,
    i.seq,
    i.kind,
    i.topic,
    i.at,
    i.until_at as until,
    i.rank,
    i.reason,
    i.evidence,
    i.placement,
    i.hold,
    i.corrects,
    i.live,
    i.flag,
    i.status,
    i.agent_state,
    i.agent_note,
    i.version,
    v.source,
    v.card,
    v.provenance,
    i.created_at,
    i.updated_at
from insights i
join insight_versions v on v.run_id = i.run_id and v.insight_id = i.insight_id and v.version = i.version;

-- Every agent run, kept after its replay is gone: how it ended and what it cost.
create table agent_runs (
    agent_run_id      text primary key,
    run_id            text not null,
    insight_id        text not null,
    facts_version     integer not null,
    cache_key         text not null,
    model             text not null,
    prompt_version    text not null,
    started_at        timestamptz not null default now(),
    finished_at       timestamptz,
    outcome           text check (outcome in ('accepted', 'rejected', 'timeout', 'error', 'superseded')),
    attempts          integer,
    input_tokens      integer,
    output_tokens     integer,
    reasoning_tokens  integer,
    latency_ms        integer,
    problems          jsonb,                -- the checks a rejected draft failed
    error             text,
    tool_calls        jsonb,                -- name and arguments of each tool call
    draft             jsonb
);

create index agent_runs_started on agent_runs (started_at);

-- Accepted drafts, reused by later replays: the same match, moment, facts, prompt and model make the
-- same job. The facts and events the agent was shown are kept so a reused draft is checked again.
create table agent_cache (
    cache_key     text primary key,
    agent_run_id  text not null,
    draft         jsonb not null,
    facts         jsonb not null,
    events        jsonb not null,
    created_at    timestamptz not null default now()
);
