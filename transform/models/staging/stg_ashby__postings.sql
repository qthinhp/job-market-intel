{{ config(materialized='view') }}

-- Ashby postings, flattened out of the raw JSON payload.
-- Richer than Greenhouse: Ashby carries an explicit remote flag, an employment
-- type, a plain-text description, and — where the company opts in — a published
-- compensation band.

with source as (

    select *
    from {{ source('raw', 'postings') }}
    where ats = 'ashby'

),

flattened as (

    select
        snapshot_date,
        ats,
        company_token,
        company_name,
        segment,
        posting_id,

        json_extract_string(payload, '$.title')            as title,
        json_extract_string(payload, '$.location')         as location_raw,
        json_extract_string(payload, '$.department')       as department,
        json_extract_string(payload, '$.team')             as team,
        json_extract_string(payload, '$.employmentType')   as employment_type,
        json_extract_string(payload, '$.jobUrl')           as job_url,

        try_cast(
            json_extract_string(payload, '$.publishedAt') as timestamptz
        )                                                  as published_at,
        cast(null as timestamptz)                          as updated_at,

        json_extract_string(payload, '$.descriptionPlain') as description_plain,
        json_extract_string(payload, '$.isRemote')         as is_remote_raw,
        json_extract_string(
            payload, '$.compensation.compensationTierSummary'
        )                                                  as compensation_summary

    from source

)

select
    company_token || ':' || posting_id as posting_key,
    snapshot_date,
    ats,
    company_token,
    company_name,
    segment,
    posting_id,
    title,
    location_raw,
    department,
    team,
    employment_type,
    job_url,
    published_at,
    updated_at,
    compensation_summary,
    coalesce(is_remote_raw = 'true', false)      as is_remote,
    nullif(trim(description_plain), '')          as description_text

from flattened
