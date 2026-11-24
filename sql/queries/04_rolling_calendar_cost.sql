-- RANGE covers seven calendar days even when a tenant skips days.
with daily as (
    select tenant_id, data_kind, cost_basis, event_date, sum(cost_usd) as usd
    from gold.fct_llm_runs
    group by tenant_id, data_kind, cost_basis, event_date
)

select
    *,
    sum(usd) over (
        partition by tenant_id, data_kind, cost_basis order by event_date
        range between interval '6 days' preceding and current row
    ) as trailing_7d_usd
from daily
order by tenant_id, data_kind, cost_basis, event_date;
