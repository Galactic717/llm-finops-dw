-- Compare only records that carry both a reported policy cost and an event-time token estimate.
select
    model_id, data_kind, cost_basis, count(*) as comparable,
    sum(charged_usd) as policy_total,
    sum(tariff_cost_usd) as final_model_token_estimate,
    sum(charged_usd - tariff_cost_usd) as difference
from gold.fct_llm_runs
where charged_usd is not null and tariff_cost_usd is not null
group by 1, 2, 3
order by 1, 2, 3;
