. "$PSScriptRoot/common.ps1"
Import-LocalConfig
Invoke-Compose @('up', '-d', '--wait', '--wait-timeout', '180', 'clickhouse', 'ollama')
Invoke-Checked uv @('run', '--frozen', 'python', 'scripts/phase0.py', 'migrate')
Invoke-Compose @('up', '-d', '--build', '--wait', '--wait-timeout', '180', 'api', 'web')
$health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 5
if ($health.status -ne 'ok' -or $health.phase -ne 0) { throw 'Health contract failed.' }
Write-Output 'Phase 0 ready: http://127.0.0.1:8080'
