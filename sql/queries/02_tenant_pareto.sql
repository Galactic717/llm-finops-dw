-- Running share of priced spend by tenant within each population and cost basis.
with spend as (
    select data_kind, cost_basis, tenant_id, sum(cost_usd) as usd
    from gold.fct_llm_runs
    where cost_usd is not null
    group by data_kind, cost_basis, tenant_id
)

select
    *,
    dense_rank() over (partition by data_kind, cost_basis order by usd desc) as cost_rank,
    sum(usd) over (
        partition by data_kind, cost_basis order by usd desc, tenant_id rows unbounded preceding
    ) / nullif(sum(usd) over (partition by data_kind, cost_basis), 0) as cumulative_share
from spend
order by data_kind, cost_basis, cost_rank, tenant_id;
