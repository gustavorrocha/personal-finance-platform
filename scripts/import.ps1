# Add what is missing from a backup archive; nothing is deleted or overwritten.
param([Parameter(Mandatory = $true)][string]$Path)
$source = (Resolve-Path -LiteralPath $Path).Path
. "$PSScriptRoot/common.ps1"
Import-LocalConfig
Invoke-Checked uv @('run', '--frozen', 'finance', 'import', $source)
