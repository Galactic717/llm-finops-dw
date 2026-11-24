-- Monthly activity retention, including the partial current month.
with active as (
    select distinct data_kind, tenant_id, date_trunc('month', event_date)::date as active_month
    from gold.fct_llm_runs
),

cohorts as (
    select *, min(active_month) over (partition by data_kind, tenant_id) as cohort_month
    from active
),

counts as (
    select data_kind, cohort_month, active_month, count(*) as active_tenants
    from cohorts
    group by data_kind, cohort_month, active_month
)

select
    *,
    active_tenants::numeric / first_value(active_tenants) over (
        partition by data_kind, cohort_month order by active_month
    ) as retained_share
from counts
order by data_kind, cohort_month, active_month;
