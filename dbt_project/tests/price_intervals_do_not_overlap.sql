with ordered as (
    select
        *,
        lead(valid_from) over (partition by price_source, model_id order by valid_from) as next_start
    from {{ ref('dim_models_scd2') }}
)

select price_version_id from ordered
where valid_to is distinct from next_start or valid_to <= valid_from
