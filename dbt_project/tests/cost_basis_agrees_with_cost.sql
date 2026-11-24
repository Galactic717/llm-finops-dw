select event_id from {{ ref('fct_llm_runs') }}
where
    (cost_basis = 'unknown') <> (cost_usd is null)
    or (cost_basis = 'simulation' and data_kind <> 'synthetic')
    or (cost_basis = 'reported' and data_kind = 'synthetic')
