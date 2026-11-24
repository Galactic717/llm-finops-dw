with ranked as (
    select
        *,
        row_number() over (
            partition by source, model_id, benchmark, revision order by observed_at desc
        ) as recency
    from {{ ref('stg_eval_scores') }}
)

select score_id, source, model_id, benchmark, score_pct, observed_at, revision
from ranked
where recency = 1
