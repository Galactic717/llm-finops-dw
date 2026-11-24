select
    r.*,
    p.price_version_id,
    r.input_tokens * p.input_usd + r.output_tokens * p.output_usd as tariff_cost_usd,
    coalesce(r.charged_usd, r.input_tokens * p.input_usd + r.output_tokens * p.output_usd) as cost_usd,
    case
        when r.data_kind = 'synthetic' and r.charged_usd is not null then 'simulation'
        when r.charged_usd is not null then 'reported'
        when
            p.price_version_id is not null and r.input_tokens is not null
            and r.output_tokens is not null then 'catalog_estimate'
        else 'unknown'
    end as cost_basis
from {{ ref('stg_llm_runs') }} as r
left join {{ ref('int_price_periods') }} as p
    on
        r.model_id = p.model_id
        and p.price_source = case when r.data_kind = 'synthetic' then 'demo' else 'openrouter' end
        and r.occurred_at >= p.valid_from
        and (r.occurred_at < p.valid_to or p.valid_to is null)
