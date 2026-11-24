-- Intent-to-treat funnel. Correctness uses valid labeled outcomes.
select
    experiment_id, data_kind, arm, assigned, successful_runs, fallbacks, correct,
    successful_runs::numeric / nullif(assigned, 0) as success_share,
    fallbacks::numeric / nullif(assigned, 0) as fallback_share,
    correct::numeric / nullif(labels_available, 0) as correct_share
from gold.mart_ab_routing
order by experiment_id, data_kind, arm;
