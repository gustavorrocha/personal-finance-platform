# Update all data: provider connections, then public rates and prices.
# Credentials come from secrets/pluggy.env in the private directory (or the environment).
param([switch]$Full)
. "$PSScriptRoot/common.ps1"
Import-LocalConfig
$arguments = @('run', '--frozen', 'finance', 'sync')
if ($Full) { $arguments += '--full' }
Invoke-Checked uv $arguments
Invoke-Checked uv @('run', '--frozen', 'finance', 'market-sync')
Write-Output 'Data updated.'
