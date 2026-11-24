{{ config(indexes=[
    {'columns': ['event_id'], 'unique': true},
    {'columns': ['tenant_id', 'event_date']},
    {'columns': ['occurred_at'], 'type': 'brin'}
]) }}
select *
from {{ ref('int_runs_with_scd2_cost') }}
