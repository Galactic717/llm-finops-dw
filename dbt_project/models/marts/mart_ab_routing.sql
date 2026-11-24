select
    experiment_id,
    data_kind,
    arm,
    count(*) as assigned,
    count(cost_usd) as priced_runs,
    count(*) filter (where status = 'ok') as successful_runs,
    count(*) filter (where fallback) as fallbacks,
    count(*) filter (where ground_truth is not null) as labels_available,
    count(*) filter (where prediction = ground_truth) as correct,
    avg(cost_usd) as mean_cost_usd,
    percentile_cont(0.95) within group (order by latency_ms) as p95_latency_ms
from {{ ref('fct_llm_runs') }}
where experiment_id is not null
group by experiment_id, data_kind, arm
