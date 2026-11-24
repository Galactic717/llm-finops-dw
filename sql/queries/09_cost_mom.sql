-- Compare only consecutive months. The latest month may be partial.
with monthly as (
    select
        data_kind, cost_basis, date_trunc('month', event_date)::date as month_start,
        sum(cost_usd) as usd
    from gold.fct_llm_runs
    where cost_usd is not null
    group by data_kind, cost_basis, month_start
),

comparison as (
    select *, lag(usd) over periods as prior_usd, lag(month_start) over periods as prior_month
    from monthly
    window periods as (partition by data_kind, cost_basis order by month_start)
)

select
    *,
    case
        when prior_month + interval '1 month' = month_start
            then 1 - usd / nullif(prior_usd, 0)
    end as savings_share
from comparison
order by data_kind, cost_basis, month_start;
