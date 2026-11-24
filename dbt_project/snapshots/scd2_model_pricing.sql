{% snapshot scd2_model_pricing %}
{{
    config(
        target_schema='snapshots',
        unique_key='price_key',
        strategy='check',
        check_cols=['input_usd', 'output_usd']
    )
}}
select distinct on (price_source, model_id)
    md5(jsonb_build_array(price_source, model_id)::text) as price_key,
    price_source,
    model_id,
    observed_at,
    input_usd,
    output_usd
from (
    select
        payload ->> 'source' as price_source,
        payload ->> 'model_id' as model_id,
        cast(payload ->> 'observed_at' as timestamptz) as observed_at,
        cast(payload ->> 'input_usd' as numeric) as input_usd,
        cast(payload ->> 'output_usd' as numeric) as output_usd
    from {{ source('bronze', 'prices') }}
) as observations
order by price_source, model_id, observed_at desc
{% endsnapshot %}
