. "$PSScriptRoot/common.ps1"
Import-LocalConfig
Invoke-Checked uv @('run', '--frozen', 'python', 'scripts/phase0.py', 'backup')
