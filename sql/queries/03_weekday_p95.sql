-- Recompute each percentile from individual latency measurements.
select
    data_kind, source, extract(isodow from event_date) as iso_weekday,
    count(latency_ms) as latency_samples,
    percentile_cont(0.95) within group (order by latency_ms) as p95_ms
from gold.fct_llm_runs
group by 1, 2, 3
order by 1, 2, 3;
