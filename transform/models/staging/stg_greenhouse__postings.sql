{{ config(materialized='view') }}

-- Greenhouse postings, flattened out of the raw JSON payload.
-- Greenhouse has no remote flag and no employment type, so `is_remote` is
-- inferred from the office name and employment type is left null rather than
-- guessed — a null we can explain beats a value we invented.

with source as (

    select *
    from {{ source('raw', 'postings') }}
    where ats = 'greenhouse'

),

flattened as (

    select
        snapshot_date,
        ats,
        company_token,
        company_name,
        segment,
        posting_id,

        json_extract_string(payload, '$.title')                    as title,
        json_extract_string(payload, '$.location.name')            as location_raw,
        json_extract_string(payload, '$.departments[0].name')      as department,
        cast(null as varchar)                                      as team,
        cast(null as varchar)                                      as employment_type,
        json_extract_string(payload, '$.absolute_url')             as job_url,

        try_cast(
            json_extract_string(payload, '$.first_published') as timestamptz
        )                                                          as published_at,
        try_cast(
            json_extract_string(payload, '$.updated_at') as timestamptz
        )                                                          as updated_at,

        json_extract_string(payload, '$.content')                  as description_html,
        cast(null as varchar)                                      as compensation_summary

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
    lower(coalesce(location_raw, '')) like '%remote%' as is_remote,
    {{ clean_html('description_html') }} as description_text

from flattened
