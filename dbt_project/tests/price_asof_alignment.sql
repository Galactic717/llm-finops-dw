select r.event_id
from {{ ref('fct_llm_runs') }} as r
inner join {{ ref('dim_models_scd2') }} as p on r.price_version_id = p.price_version_id
where
    r.occurred_at < p.valid_from
    or r.occurred_at >= p.valid_to
    or r.model_id <> p.model_id
    or r.tariff_cost_usd is distinct from r.input_tokens * p.input_usd + r.output_tokens * p.output_usd
