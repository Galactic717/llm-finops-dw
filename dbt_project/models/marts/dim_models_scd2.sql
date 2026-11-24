select
    price_version_id, model_id, price_source, input_usd, output_usd, valid_from, valid_to,
    valid_to is null as is_current
from {{ ref('int_price_periods') }}
