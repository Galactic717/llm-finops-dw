param(
    [string]$Container = 'verstak-agent-postgres-1',
    [string]$OutputPath = "$PSScriptRoot/../data/private/verstak.jsonl"
)
$ErrorActionPreference = 'Stop'
$lines = Get-Content -Raw -LiteralPath "$PSScriptRoot/../sql/export_verstak.sql" |
    docker exec -i $Container sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At'
if ($LASTEXITCODE -ne 0) { throw "Verstak export failed" }
$dir = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$lines | Set-Content -Encoding utf8 -LiteralPath $OutputPath
Write-Output "Exported $($lines.Count) completed workflow runs to $OutputPath"
