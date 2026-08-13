{{ config(materialized='view') }}

-- One posting shape across every ATS. Downstream models never need to know
-- which vendor a posting came from.
--
-- union all, not union: posting_key is unique per company per snapshot, so
-- there is nothing to deduplicate, and dropping the implicit distinct keeps
-- this cheap as snapshot history grows.

with unioned as (

    select * from {{ ref('stg_greenhouse__postings') }}
    union all
    select * from {{ ref('stg_ashby__postings') }}

)

select
    posting_key,
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
    is_remote,
    description_text,

    -- Companies fan one role out across many cities: Databricks posts
    -- "Solutions Architect" 17 times for 16 locations. Each is a distinct
    -- posting, but counting them as 17 openings overstates hiring. This key
    -- collapses that fan-out so demand can be measured at either grain.
    md5(company_token || '|' || lower(trim(title))) as requisition_key,

    -- Coarse seniority read off the title. Deliberately conservative: anything
    -- that doesn't clearly signal a level becomes 'unspecified' rather than
    -- being bucketed as mid by default, which would inflate that band.
    case
        when regexp_matches(lower(title), '\b(intern|internship)\b')            then 'intern'
        when regexp_matches(lower(title), '\b(new grad|university grad)\b')     then 'entry'
        when regexp_matches(lower(title), '\b(vp|vice president|head of|director|chief)\b')
                                                                                then 'executive'
        when regexp_matches(lower(title), '\b(principal|staff|distinguished|fellow)\b')
                                                                                then 'staff+'
        when regexp_matches(lower(title), '\b(senior|sr\.?|lead)\b')            then 'senior'
        when regexp_matches(lower(title), '\b(junior|jr\.?|associate|entry)\b') then 'entry'

        -- Level numerals, but never on a management title. "Manager I" is a
        -- first-line manager, not an entry-level hire, and the bare "I" would
        -- otherwise match and bury it in the entry band.
        when not regexp_matches(lower(title), '\b(manager|director|vp|head|chief|principal)\b')
             and regexp_matches(lower(title), '\b(ii|iii|2|3)\b')               then 'mid'
        when not regexp_matches(lower(title), '\b(manager|director|vp|head|chief|principal)\b')
             and regexp_matches(lower(title), '\b(i|1)\b')                      then 'entry'

        else 'unspecified'
    end as seniority_band,

    -- Manager-in-title is tracked separately from seniority. Folding it into
    -- the seniority ladder would silently merge senior ICs with people
    -- managers, which are different markets with different skill demands.
    regexp_matches(lower(title), '\b(manager|management|head of|director|vp|chief)\b')
        and not regexp_matches(lower(title), '\b(product manager|program manager|project manager|account manager|success manager|community manager)\b')
        as is_people_leadership,

    -- Job family, from the title. Order matters throughout: specific patterns
    -- must fire before the generic ones that would otherwise swallow them
    -- ('data engineer' before 'engineer', 'solutions engineer' before
    -- 'software engineer').
    case
        when regexp_matches(lower(title), 'analytics engineer')                  then 'analytics engineering'
        when regexp_matches(lower(title), 'data (scientist|science)')            then 'data science'
        when regexp_matches(lower(title), '\b(machine learning|ml|ai) engineer') then 'ml engineering'
        when regexp_matches(lower(title), '\b(research scientist|research engineer)') then 'research'
        when regexp_matches(lower(title), 'data engineer')                       then 'data engineering'
        when regexp_matches(lower(title), '(data|business|bi|financial|quantitative) analyst')
                                                                                 then 'analytics'
        when regexp_matches(lower(title), '\b(analytics|business intelligence|bizops|business operations)\b')
                                                                                 then 'analytics'
        when regexp_matches(lower(title), '(solutions?|sales|field|forward deployed|partner) (architect|engineer)')
                                                                                 then 'solutions engineering'
        when regexp_matches(lower(title), '(customer success|technical account|support engineer|customer engineer)')
                                                                                 then 'customer success'
        when regexp_matches(lower(title), '\b(security|infosec|trust and safety|privacy)\b')
                                                                                 then 'security'
        when regexp_matches(lower(title), '\b(sre|site reliability|infrastructure|platform|devops|systems) engineer')
                                                                                 then 'infrastructure'
        when regexp_matches(lower(title), '(software|backend|back.end|frontend|front.end|full.?stack|mobile|ios|android|web) engineer')
                                                                                 then 'software engineering'
        when regexp_matches(lower(title), '(product manager|product management|product lead)')
                                                                                 then 'product'
        when regexp_matches(lower(title), '\b(designer|design|ux|ui)\b')         then 'design'
        when regexp_matches(lower(title), '(account executive|account manager|sales|revenue|deal desk|business development)')
                                                                                 then 'sales'
        when regexp_matches(lower(title), '(recruiter|recruiting|people|talent|hr\b|compensation)')
                                                                                 then 'people'
        when regexp_matches(lower(title), '(marketing|growth|brand|content|communications)')
                                                                                 then 'marketing'
        when regexp_matches(lower(title), '\b(counsel|legal|attorney|paralegal|compliance)\b')
                                                                                 then 'legal'
        when regexp_matches(lower(title), '\b(finance|accounting|controller|treasury|fp&a|audit)\b')
                                                                                 then 'finance'
        when regexp_matches(lower(title), '\b(operations|program manager|project manager|chief of staff|strategy)\b')
                                                                                 then 'operations'
        when regexp_matches(lower(title), '\bengineer\b')                        then 'software engineering'
        else 'other'
    end as job_family

from unioned
