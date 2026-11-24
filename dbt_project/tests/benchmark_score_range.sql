select score_id from {{ ref('mart_model_benchmarks') }}
where score_pct not between 0 and 100
