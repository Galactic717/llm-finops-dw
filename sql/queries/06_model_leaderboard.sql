-- Latest observation per revision, then rank one revision per model and benchmark.
with newest as (
    select
        *,
        row_number() over (
            partition by source, model_id, benchmark order by observed_at desc, revision desc
        ) as rn
    from gold.mart_model_benchmarks
)

select
    benchmark, source, model_id, revision, score_pct,
    dense_rank() over (partition by source, benchmark order by score_pct desc) as rank
from newest
where rn = 1
order by benchmark, source, rank, model_id;
