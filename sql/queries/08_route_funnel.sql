-- Intent-to-treat funnel. Correctness requires labels for every assignment.
select
    experiment_id, data_kind, arm, assigned, successful_runs, fallbacks, correct,
    successful_runs::numeric / nullif(assigned, 0) as success_share,
    fallbacks::numeric / nullif(assigned, 0) as fallback_share,
    case when labels_available = assigned then correct::numeric / nullif(assigned, 0) end
        as correct_share
from gold.mart_ab_routing
order by experiment_id, data_kind, arm;
