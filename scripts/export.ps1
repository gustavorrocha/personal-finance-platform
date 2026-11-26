# Write a backup archive: your edits (Parquet) and the original provider captures.
# By default it goes to the private folder's exports directory, outside Git and cloud sync.
param([string]$Path)
. "$PSScriptRoot/common.ps1"
Import-LocalConfig
if (-not $Path) {
    $exports = Join-Path $env:FINANCE_PRIVATE_DIR 'exports'
    New-Item -ItemType Directory -Force -Path $exports | Out-Null
    $Path = Join-Path $exports "finance-backup-$(Get-Date -Format yyyy-MM-dd).zip"
}
$target = [IO.Path]::GetFullPath($Path)
Invoke-Checked uv @('run', '--frozen', 'finance', 'export', $target)
Write-Output "Backup written to $target"
