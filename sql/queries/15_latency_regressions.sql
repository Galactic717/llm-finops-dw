-- Compare adjacent active dates within a workflow and source.
with daily as (
    select
        event_date, data_kind, source, workflow, count(latency_ms) as observations,
        percentile_cont(0.95) within group (order by latency_ms) as p95_ms
    from gold.fct_llm_runs
    group by event_date, data_kind, source, workflow
)

select
    *,
    p95_ms - lag(p95_ms) over timeline as p95_change_ms,
    event_date - lag(event_date) over timeline as gap_days
from daily
window timeline as (partition by data_kind, source, workflow order by event_date)
order by data_kind, source, workflow, event_date;
