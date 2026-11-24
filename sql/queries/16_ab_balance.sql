-- Assignment counts by tenant. Global SRM is computed in the experiment notebook.
select
    experiment_id, data_kind, tenant_id,
    count(*) filter (where arm = 'all_cloud') as all_cloud,
    count(*) filter (where arm = 'hybrid') as hybrid
from gold.fct_llm_runs
where experiment_id is not null
group by 1, 2, 3
order by 1, 2, 3;
