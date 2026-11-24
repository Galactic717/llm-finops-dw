with sequenced as (
    select
        *,
        lag(input_usd) over price_order as previous_input,
        lag(output_usd) over price_order as previous_output
    from {{ ref('stg_model_pricing') }}
    window price_order as (partition by price_source, model_id order by observed_at)
),

changes as (
    select *
    from sequenced
    where input_usd is distinct from previous_input or output_usd is distinct from previous_output
)

select
    md5(observation_id) as price_version_id,
    model_id,
    price_source,
    input_usd,
    output_usd,
    observed_at as valid_from,
    lead(observed_at) over (partition by price_source, model_id order by observed_at) as valid_to
from changes
