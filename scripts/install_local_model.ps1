. "$PSScriptRoot/common.ps1"
Import-LocalConfig
$models = Join-Path $env:FINANCE_PRIVATE_DIR 'models'
if (-not (Test-Path -LiteralPath $models -PathType Container) -or
    ((Get-Item -LiteralPath $models -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw 'Expected a local models directory from bootstrap.'
}

$downloader = 'finance-model-download-' + [Guid]::NewGuid().ToString('N')
Invoke-Checked docker @(
    'run', '-d', '--name', $downloader, '--network', 'bridge',
    '--user', '10001:10001', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
    '--mount', "type=bind,source=$models,target=/models",
    '-e', 'OLLAMA_MODELS=/models', '-e', 'OLLAMA_NO_CLOUD=1',
    '-e', 'OLLAMA_HOST=127.0.0.1:11434', '-e', 'HOME=/tmp',
    'ollama/ollama:0.40.16', 'serve'
)
try {
    $ready = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        & docker exec $downloader ollama list 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw 'Temporary model downloader did not become ready.' }
    Invoke-Checked docker @('exec', $downloader, 'ollama', 'pull', 'qwen3:1.7b')
} finally {
    & docker rm -f $downloader | Out-Null
}
Write-Output 'Local model installed. Start or update the private services with scripts/run_local.ps1.'
