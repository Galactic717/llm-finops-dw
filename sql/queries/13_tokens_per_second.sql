-- Request-level observed throughput for successful calls with measured usage.
select
    data_kind, source, model_id, count(*) as measurements,
    percentile_cont(0.5) within group (order by output_tokens * 1000.0 / latency_ms) as median_tps
from gold.fct_llm_runs
where status = 'ok' and output_tokens is not null and latency_ms > 0
group by 1, 2, 3
order by 1, 2, 3;
