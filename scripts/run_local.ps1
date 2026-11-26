. "$PSScriptRoot/common.ps1"
Import-LocalConfig
$gui = @(docker ps -aq --filter 'label=com.docker.compose.project=personal-finance' --filter 'label=com.docker.compose.service=clickhouse-gui')
if ($LASTEXITCODE -ne 0) { throw 'Could not check the local ClickHouse GUI container.' }
$compose = Get-ComposeArguments -WithGui:($gui.Count -ne 0)
$dashboardServices = @('api', 'web')
if ($gui.Count -ne 0) { $dashboardServices += 'clickhouse-gui' }
Invoke-Checked uv @('run', '--frozen', 'python', '-m', 'scripts.configure_dashboard')
Invoke-Checked docker ($compose + @('up', '-d', '--wait', '--wait-timeout', '180', 'clickhouse', 'ollama'))
Invoke-Checked uv @('run', '--frozen', 'python', 'scripts/phase0.py', 'migrate')
Invoke-Checked docker ($compose + @('up', '-d', '--build', '--wait', '--wait-timeout', '180') + $dashboardServices)
$health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 5
if ($health.status -ne 'ok' -or $health.phase -ne 0) { throw 'Health contract failed.' }
# The sync agent runs the updates requested from the dashboard; restart it with the stack.
$agentPid = Join-Path $env:FINANCE_PRIVATE_DIR 'sync-agent.pid'
if (Test-Path -LiteralPath $agentPid) {
    $previous = (Get-Content -LiteralPath $agentPid -Raw).Trim()
    if ($previous -match '^\d+$' -and (Get-Process -Id $previous -ErrorAction SilentlyContinue)) {
        & taskkill.exe /PID $previous /T /F | Out-Null
    }
}
$agent = Start-Process -FilePath 'uv' -ArgumentList @('run', '--frozen', 'finance', 'sync-agent') `
    -WindowStyle Hidden -PassThru
Set-Content -LiteralPath $agentPid -Value $agent.Id -Encoding ascii
Write-Output 'Phase 0 ready: http://127.0.0.1:8080'
