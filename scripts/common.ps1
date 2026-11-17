Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $script:RepoRoot
$env:UV_CACHE_DIR = Join-Path $script:RepoRoot '.uv-cache'

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed: $Program (exit $LASTEXITCODE)" }
}

function Import-LocalConfig {
    $config = Join-Path $script:RepoRoot '.env'
    if (-not (Test-Path -LiteralPath $config)) { throw 'Run scripts/bootstrap.ps1 first.' }
    $lines = @(Get-Content -LiteralPath $config | Where-Object { $_ -match '^FINANCE_PRIVATE_DIR=' })
    if ($lines.Count -ne 1) { throw 'Expected one FINANCE_PRIVATE_DIR in .env.' }
    $env:FINANCE_PRIVATE_DIR = $lines[0].Substring('FINANCE_PRIVATE_DIR='.Length)
    Invoke-Checked uv @('run', '--frozen', 'python', 'scripts/phase0.py', 'validate-path')
    $marker = Join-Path $env:FINANCE_PRIVATE_DIR '.finance-phase0'
    if (-not (Test-Path -LiteralPath $marker) -or
        (Get-Content -LiteralPath $marker -Raw).Trim() -ne 'synthetic-only-v1') {
        throw 'Private directory is not owned by this Phase 0 setup.'
    }
}

function Invoke-Compose {
    param([string[]]$ComposeArguments)
    Invoke-Checked docker (@('compose', '--env-file', '.env', '-f', 'infra/compose.yaml') + $ComposeArguments)
}
