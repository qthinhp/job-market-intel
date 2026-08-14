-- The bridge's grain is one row per posting per skill per snapshot. A
-- duplicate would mean two taxonomy rows share a canonical skill name, and
-- every "postings mentioning X" count downstream would double for that skill.

select
    posting_key,
    skill,
    snapshot_date,
    count(*) as rows_at_grain

from {{ ref('fct_posting_skill') }}

group by posting_key, skill, snapshot_date
having count(*) > 1
