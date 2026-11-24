select model_id from {{ ref('stg_llm_runs') }}
union
select model_id from {{ ref('stg_model_pricing') }}
