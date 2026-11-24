-- Effective price changes including a model's first observed rate.
select
    model_id, price_source, valid_from, valid_to, input_usd, output_usd,
    input_usd - lag(input_usd) over version_order as delta_input,
    lead(input_usd) over version_order as next_input
from gold.dim_models_scd2
window version_order as (partition by price_source, model_id order by valid_from)
order by price_source, model_id, valid_from;
