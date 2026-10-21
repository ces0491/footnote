-- Spanish and French versions of each card's wording (docs/overlay.md). The agents service
-- translates the version of each live card viewers see with Azure AI Translator, and code checks that
-- every figure and name came through; a translation that fails the check is kept with its problems
-- and never shown.
create table card_translations (
    run_id      text not null,
    insight_id  text not null,
    version     integer not null,
    lang        text not null check (lang in ('es', 'fr')),
    card        jsonb,           -- headline, casual and analyst in that language; null when it failed the check
    problems    jsonb,           -- what the check found, when it failed
    created_at  timestamptz not null default now(),
    primary key (run_id, insight_id, version, lang),
    foreign key (run_id, insight_id, version) references insight_versions (run_id, insight_id, version) on delete cascade
);

-- Every replay is the same match, so the same English wording comes round again: a translation is
-- kept under a hash of the text and the names it protects, and reused.
create table translation_cache (
    cache_key   text not null,
    lang        text not null,
    card        jsonb,
    problems    jsonb,
    created_at  timestamptz not null default now(),
    primary key (cache_key, lang)
);

-- What viewers get for an insight gains its translations: those of the version they see that passed
-- the check, by language.
create or replace view insight_cards as
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
    i.updated_at,
    (select coalesce(jsonb_object_agg(t.lang, t.card), '{}'::jsonb)
       from card_translations t
      where t.run_id = i.run_id and t.insight_id = i.insight_id and t.version = i.version and t.card is not null
    ) as translations
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
