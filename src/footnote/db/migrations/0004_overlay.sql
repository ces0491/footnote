-- The overlay contract (docs/overlay.md), the producer's desk, delivery held to each viewer's
-- playback, and the tracking the pitch view draws.

-- Who started each run, and how its graphics are approved. The viewer is the anonymous ID of the
-- browser that started the replay: only that viewer may produce it, and no view or API serves it.
-- 'auto' approves each live insight as it is found; 'manual' leaves it for the producer.
alter table runs add column viewer text;
alter table runs add column producer text not null default 'auto' check (producer in ('auto', 'manual'));

-- Each live row's push as viewers were sent it, timing aside, and at the end of the backfill the
-- snapshot. A viewer whose stream runs behind live rebuilds the match as of their own playback from
-- these rather than from the live state.
alter table feed_events add column push jsonb;

-- Presentation hints the processor sets beside placement and hold.
alter table insights add column duration real;  -- seconds of match time on screen; null in the side panel
alter table insights add column motion text not null default 'still' check (motion in ('still', 'animated'));

-- A graphic is approved, by the producer or automatically, then may be withdrawn; or it is killed
-- before it airs. Being on air is a span of playback, not a stored status.
alter table insights drop constraint insights_status_check;
alter table insights add constraint insights_status_check
    check (status in ('drafted', 'approved', 'withdrawn', 'killed'));

-- A producer's edit is a version of its own, checked like the others.
alter table insight_versions drop constraint insight_versions_source_check;
alter table insight_versions add constraint insight_versions_source_check
    check (source in ('template', 'agent', 'producer'));

-- What viewers get for an insight: one item of the overlay contract. `shown_seq` is the feed message
-- behind the item's current state (found, restated, or flagged by VAR or a correction), and
-- `shown_at` its match time: each client holds the item until its own playback reaches it.
-- `fields` holds every fact's text, for graphics systems that fill a template's fields themselves.
drop view insight_cards;
create view insight_cards as
select
    i.run_id,
    r.match_id,
    i.insight_id,
    i.seq,
    i.kind,
    i.topic,
    i.at,
    i.until_at as until,
    shown.seq as shown_seq,
    shown.at as shown_at,
    shown.ts,
    i.rank,
    i.reason,
    i.evidence,
    i.placement,
    i.hold,
    i.duration,
    i.motion,
    i.corrects,
    i.live,
    i.flag,
    i.status,
    i.status_by,
    i.status_at,
    i.agent_state,
    i.agent_note,
    i.version,
    v.source,
    v.card,
    (select coalesce(jsonb_object_agg(f.key, f.value -> 'display'), '{}'::jsonb) from jsonb_each(i.facts) f) as fields,
    v.provenance,
    i.created_at,
    i.updated_at
from insights i
join runs r on r.run_id = i.run_id
join insight_versions v on v.run_id = i.run_id and v.insight_id = i.insight_id and v.version = i.version
left join lateral (
    select e.seq,
           jsonb_build_object(
               'period', e.period,
               't', (e.body ->> 't')::float8,
               'minute', (e.body ->> 'minute')::int,
               'added_minute', e.body -> 'added_minute'
           ) as at,
           e.body ->> 'ts' as ts
      from feed_events e
     where e.run_id = i.run_id and e.seq = greatest(i.seq, coalesce((i.flag ->> 'seq')::int, 0))
) shown on true;

-- Player and ball positions for the pitch view, from the committed tracking file, served to a run's
-- viewers no further than its live point. `matches.tracking` says how the chunks are laid out.
alter table matches add column tracking jsonb;

create table tracking_chunks (
    match_id  text not null references matches (match_id) on delete cascade,
    period    smallint not null,
    chunk     integer not null,  -- chunk n starts at frame n times the frames per chunk
    frames    bytea not null,    -- little-endian int16 values per frame (src/footnote/live/pitch.py)
    primary key (match_id, period, chunk)
);
