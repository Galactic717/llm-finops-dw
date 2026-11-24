-- Error rate and denominator by workflow plus individual source.
select
    data_kind, source, workflow, count(*) as total,
    count(*) filter (where status = 'error') as errors,
    avg((status = 'error')::integer) as error_rate
from gold.fct_llm_runs
group by grouping sets ((data_kind, source, workflow), (data_kind, source))
order by data_kind, source, workflow nulls last;
