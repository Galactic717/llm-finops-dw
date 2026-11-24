select
    event_date,
    tenant_id,
    workflow,
    model_id,
    data_kind,
    source,
    cost_basis,
    count(*) as runs,
    count(cost_usd) as priced_runs,
    count(*) filter (where status = 'ok') as successful_runs,
    sum(input_tokens) as input_tokens,
    sum(output_tokens) as output_tokens,
    sum(cost_usd) as cost_usd,
    percentile_cont(0.95) within group (order by latency_ms) as p95_latency_ms
from {{ ref('fct_llm_runs') }}
group by event_date, tenant_id, workflow, model_id, data_kind, source, cost_basis
