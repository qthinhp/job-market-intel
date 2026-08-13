-- Grain: one row per posting per day it was observed open.
--
-- The fact table stays thin — keys, dates, and the flags needed to slice
-- without joining back to the dimension. Descriptive attributes live in
-- dim_posting.
--
-- Two additive measures are provided because they answer different questions:
-- `posting_count` counts listings, `requisition_weight` counts roles, splitting
-- a role posted across N cities into N fractions that sum to 1.

with postings as (

    select * from {{ ref('int_postings__unioned') }}

),

fan_out as (

    select
        snapshot_date,
        requisition_key,
        count(*) as postings_in_requisition
    from postings
    group by snapshot_date, requisition_key

)

select
    postings.posting_key,
    postings.requisition_key,
    postings.snapshot_date,
    postings.company_token,

    postings.job_family,
    postings.seniority_band,
    postings.is_people_leadership,
    postings.is_remote,
    postings.compensation_summary is not null as has_disclosed_pay,

    1 as posting_count,
    1.0 / fan_out.postings_in_requisition as requisition_weight

from postings
join fan_out
    on postings.snapshot_date = fan_out.snapshot_date
    and postings.requisition_key = fan_out.requisition_key
