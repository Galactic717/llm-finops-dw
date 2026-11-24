select
    key as score_id,
    payload ->> 'source' as source,
    payload ->> 'model_id' as model_id,
    payload ->> 'benchmark' as benchmark,
    cast(payload ->> 'score' as double precision) as score_pct,
    cast(payload ->> 'observed_at' as timestamptz) as observed_at,
    payload ->> 'revision' as revision
from {{ source('bronze', 'scores') }}
