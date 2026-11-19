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
Write-Output 'Phase 0 ready: http://127.0.0.1:8080'
