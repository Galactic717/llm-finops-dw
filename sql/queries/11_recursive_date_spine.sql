-- Recursive calendar. Missing events count as zero activity.
with recursive bounds as (
    select min(event_date) as first_day, max(event_date) as last_day from gold.fct_llm_runs
),

calendar (event_date) as (
    select first_day from bounds where first_day is not null
    union all
    select c.event_date + 1
    from calendar as c
    cross join bounds as b
    where c.event_date < b.last_day
),

daily as (
    select event_date, count(*) as runs from gold.fct_llm_runs
    where data_kind = 'synthetic'
    group by event_date
)

select c.event_date, coalesce(d.runs, 0) as synthetic_runs
from calendar as c
left join daily as d using (event_date)
order by c.event_date;
