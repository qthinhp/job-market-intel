-- Grain: one row per posting per skill per snapshot date.
--
-- A many-to-many bridge between postings and the curated skill taxonomy in
-- seeds/skills.csv. Deliberately built with regex matching rather than an LLM:
-- the skills that matter most here are named tools, and "Snowflake" in a job
-- description is a literal string, not an inference problem. Matching is
-- free, deterministic, reruns identically, and needs no API key in CI.
--
-- The tradeoff is real and worth stating: this finds skills that are *named*,
-- and misses ones that are only implied ("comfortable with modern data
-- tooling"). It also cannot tell required from nice-to-have. Both are jobs an
-- LLM does well, and the intended next step is to sample a few hundred
-- postings through one, compare against these matches, and fold whatever the
-- patterns missed back into the taxonomy — using the model to improve the
-- cheap pipeline rather than to replace it.
--
-- Every pattern carries a confidence rating in the seed. Short or ambiguous
-- tokens (R, Java, SAS) are rated below high and should be read with care;
-- see the seed for the specific guard on each.

with postings as (

    select
        posting_key,
        snapshot_date,
        company_token,
        job_family,
        seniority_band,
        is_remote,
        -- Lowercased once here rather than per skill: this CTE is scanned once
        -- and then matched against ~100 patterns, so the cast would otherwise
        -- run 100 times per posting.
        lower(description_text) as description_lower
    from {{ ref('int_postings__unioned') }}
    where description_text is not null

),

taxonomy as (

    select
        skill,
        category,
        pattern,
        confidence
    from {{ ref('skills') }}

)

select
    postings.posting_key,
    postings.snapshot_date,
    postings.company_token,
    postings.job_family,
    postings.seniority_band,
    postings.is_remote,

    taxonomy.skill,
    taxonomy.category    as skill_category,
    taxonomy.confidence  as match_confidence,

    1 as mention_count

from postings
cross join taxonomy
where regexp_matches(postings.description_lower, taxonomy.pattern)
