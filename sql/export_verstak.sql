-- Export workflow-level telemetry. No input text, proposal, or verification payloads.
with attempt_totals as (
    select
        run_id,
        case when count(*) = count(input_tokens) then sum(input_tokens) end as input_tokens,
        case when count(*) = count(output_tokens) then sum(output_tokens) end as output_tokens
    from model_attempts
    group by run_id
)

select
    jsonb_build_object(
        'event_id', 'verstak:' || r.id::text,
        'occurred_at', r.created_at,
        'tenant_id', 'verstak-' || substr(md5(r.tenant), 1, 16),
        'workflow', 'case_triage_e2e',
        'model_id', 'verstak/aggregate',
        'data_kind', 'observed',
        'source', 'verstak',
        'status', case r.status
            when 'succeeded' then 'ok'
            when 'rejected' then 'rejected'
            else 'error'
        end,
        'input_tokens', a.input_tokens,
        'output_tokens', a.output_tokens,
        'latency_ms', extract(epoch from (r.finished_at - r.created_at)) * 1000,
        'charged_usd', r.cost_micros::numeric / 1000000
    )
from workflow_runs as r
left join attempt_totals as a on a.run_id = r.id
where r.status in ('succeeded', 'rejected', 'failed') and r.finished_at > r.created_at
order by r.id;
