-- Daily inferred spend and pricing coverage. NULL spend means there were no known costs.
select
    event_date, data_kind, cost_basis, count(*) as runs, count(cost_usd) as priced,
    sum(cost_usd) as total_usd, 1000 * avg(cost_usd) as usd_per_1000_priced_runs
from gold.fct_llm_runs
group by event_date, data_kind, cost_basis
order by event_date, data_kind, cost_basis;
