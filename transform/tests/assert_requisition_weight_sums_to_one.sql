-- The whole point of requisition_weight is that a role fanned out across N
-- cities still counts as exactly one role. If this ever fails, every
-- "roles by family" number in the report is silently wrong — which is the
-- kind of error a dashboard will never show you.
--
-- Tolerance accounts for floating point: 1/3 + 1/3 + 1/3 != 1.0 exactly.

select
    snapshot_date,
    requisition_key,
    sum(requisition_weight) as total_weight

from {{ ref('fct_posting_snapshot') }}

group by snapshot_date, requisition_key
having abs(sum(requisition_weight) - 1.0) > 0.000001
