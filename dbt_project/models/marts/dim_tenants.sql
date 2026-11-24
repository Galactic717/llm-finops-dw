select
    tenant_id,
    min(event_date) as first_seen_date,
    max(event_date) as last_seen_date
from {{ ref('stg_llm_runs') }}
group by tenant_id
