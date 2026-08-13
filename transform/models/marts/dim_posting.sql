-- One row per posting ever observed, carrying its latest known attributes plus
-- its lifecycle across snapshots.
--
-- This is the model that makes daily snapshotting worth the trouble: once a
-- posting disappears from the source API, `is_open` goes false and
-- `last_seen_date` freezes, so time-to-fill becomes measurable. With a single
-- snapshot every posting looks new — the history has to accumulate.
--
-- `description_text` is deliberately excluded: it averages 6 KB and would make
-- this dimension ~35 MB. It stays in the staging layer where the skill
-- extraction step reads it.

with postings as (

    select * from {{ ref('int_postings__unioned') }}

),

bounds as (

    select max(snapshot_date) as latest_snapshot_date from postings

),

lifecycle as (

    select
        posting_key,
        min(snapshot_date)          as first_seen_date,
        max(snapshot_date)          as last_seen_date,
        count(distinct snapshot_date) as snapshots_observed
    from postings
    group by posting_key

),

latest_attributes as (

    -- A posting's title or location can be edited while it is open, so the
    -- dimension tracks the most recent version rather than the first.
    select * exclude (rn)
    from (
        select
            *,
            row_number() over (
                partition by posting_key
                order by snapshot_date desc
            ) as rn
        from postings
    )
    where rn = 1

)

select
    attrs.posting_key,
    attrs.requisition_key,
    attrs.posting_id,
    attrs.ats,

    attrs.company_token,
    attrs.company_name,
    attrs.segment,

    attrs.title,
    attrs.job_family,
    attrs.seniority_band,
    attrs.is_people_leadership,
    attrs.department,
    attrs.team,
    attrs.employment_type,

    attrs.location_raw,
    attrs.is_remote,

    attrs.job_url,
    attrs.compensation_summary,
    attrs.compensation_summary is not null as has_disclosed_pay,

    attrs.published_at,
    life.first_seen_date,
    life.last_seen_date,
    life.snapshots_observed,

    life.last_seen_date = bounds.latest_snapshot_date as is_open,

    -- Age of the posting at the source, available from snapshot one.
    date_diff('day', cast(attrs.published_at as date), life.last_seen_date)
        as days_since_published,

    -- Only meaningful once a posting has closed; null while it is still open.
    case
        when life.last_seen_date < bounds.latest_snapshot_date
        then date_diff('day', life.first_seen_date, life.last_seen_date)
    end as days_observed_open

from latest_attributes as attrs
join lifecycle as life using (posting_key)
cross join bounds
