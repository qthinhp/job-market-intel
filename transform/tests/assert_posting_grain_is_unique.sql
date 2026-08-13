-- The fact table's declared grain is one row per posting per snapshot date.
-- A duplicate here means the union or the fan-out join has started double
-- counting, which would inflate every measure downstream.

select
    posting_key,
    snapshot_date,
    count(*) as rows_at_grain

from {{ ref('fct_posting_snapshot') }}

group by posting_key, snapshot_date
having count(*) > 1
