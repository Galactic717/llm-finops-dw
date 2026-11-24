param(
    [string]$LlamaRoot = "$env:LOCALAPPDATA/Programs/llama.cpp",
    [string]$ModelPath = "$PSScriptRoot/../../verifine-slm/artifacts/verifine-qwen-Q4_K_M.gguf",
    [int]$Port = 9941,
    [int]$GpuLayers = 99
)
$ErrorActionPreference = 'Stop'
$binary = Join-Path $LlamaRoot 'llama-server.exe'
$localModel = (Resolve-Path -LiteralPath $ModelPath).Path
& $binary --model $localModel --alias verifine-qwen-q4 --host 127.0.0.1 --port $Port `
    --ctx-size 2048 --parallel 1 --gpu-layers $GpuLayers --offline
exit $LASTEXITCODE
