with fact as (
    select
        experiment_id,
        data_kind,
        arm,
        count(*) as assigned,
        count(cost_usd) as priced
    from {{ ref('fct_llm_runs') }}
    where arm is not null
    group by experiment_id, data_kind, arm
)
select coalesce(f.experiment_id, m.experiment_id) as experiment_id
from fact as f
full outer join {{ ref('mart_ab_routing') }} as m using (experiment_id, data_kind, arm)
where f.assigned is distinct from m.assigned or f.priced is distinct from m.priced_runs
