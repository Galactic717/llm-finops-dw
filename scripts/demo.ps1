param(
    [switch]$Offline,
    [switch]$WithAirflow
)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$env:OMP_NUM_THREADS = '2'
Push-Location (Join-Path $PSScriptRoot '..')
try {
    docker compose up -d --wait warehouse metabase
    uv sync --locked --group analysis
    uv run --locked --no-sync python -m ingestion.ingest_verstak_logs demo --end 2026-11-24
    if (-not $Offline) {
        uv run --locked --no-sync python -m ingestion.fetch_open_models
    }
    uv run --locked --no-sync python -m ingestion.warehouse ingest
    uv run --locked --no-sync dbt build --project-dir dbt_project --profiles-dir dbt_project
    uv run --locked --no-sync python -m analysis.routing
    uv run --locked --no-sync python -m bi.export
    uv run --locked --no-sync python -m bi.powerbi
    uv run --locked --no-sync python -m bi.metabase --public-demo
    if ($WithAirflow) {
        docker compose up -d --wait airflow-web airflow-scheduler
    }
}
finally {
    Pop-Location
}
