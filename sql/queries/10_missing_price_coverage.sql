-- Distinguish incomplete usage, unpriced models, and known costs.
select
    data_kind, source, model_id, count(*) as runs,
    count(*) filter (where cost_usd is null) as unknown_cost,
    count(*) filter (where price_version_id is null) as no_catalog_tariff,
    count(*) filter (where input_tokens is null or output_tokens is null) as missing_usage
from gold.fct_llm_runs
group by data_kind, source, model_id
order by unknown_cost desc, data_kind, source, model_id;
