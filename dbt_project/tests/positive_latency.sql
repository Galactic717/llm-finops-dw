select event_id from {{ ref('fct_llm_runs') }}
where latency_ms <= 0 or ttft_ms <= 0 or ttft_ms > latency_ms
