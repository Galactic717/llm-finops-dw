select
    key as observation_id,
    payload ->> 'model_id' as model_id,
    payload ->> 'source' as price_source,
    cast(payload ->> 'observed_at' as timestamptz) as observed_at,
    cast(payload ->> 'input_usd' as numeric) as input_usd,
    cast(payload ->> 'output_usd' as numeric) as output_usd
from {{ source('bronze', 'prices') }}
