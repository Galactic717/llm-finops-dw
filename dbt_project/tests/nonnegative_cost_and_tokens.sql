select event_id from {{ ref('fct_llm_runs') }}
where cost_usd < 0 or tariff_cost_usd < 0 or input_tokens < 0 or output_tokens < 0
