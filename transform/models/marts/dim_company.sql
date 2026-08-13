-- One row per tracked company, with its hiring profile as of the latest
-- snapshot. Small enough that Power BI can hold it entirely in memory.

with postings as (

    select * from {{ ref('int_postings__unioned') }}

),

latest as (

    select * from postings
    where snapshot_date = (select max(snapshot_date) from postings)

)

select
    company_token,
    company_name,
    segment,
    any_value(ats)                                   as ats,

    count(*)                                         as open_postings,
    count(distinct requisition_key)                  as open_requisitions,
    count(distinct job_family)                       as job_families,

    sum(case when is_remote then 1 else 0 end)       as remote_postings,
    round(100.0 * avg(case when is_remote then 1 else 0 end), 1) as pct_remote,
    round(100.0 * avg(case when compensation_summary is not null then 1 else 0 end), 1)
                                                     as pct_with_pay_disclosed,

    -- Fan-out ratio: postings per distinct role. A company at 1.0 posts each
    -- role once; Databricks sits near 2.0 because it lists the same role in
    -- every city it will hire for. Comparing raw posting counts across
    -- companies without this is misleading.
    round(count(*)::decimal / nullif(count(distinct requisition_key), 0), 2)
                                                     as postings_per_requisition,

    min(published_at)                                as oldest_posting_at,
    max(published_at)                                as newest_posting_at,
    max(snapshot_date)                               as as_of_date

from latest
group by company_token, company_name, segment
