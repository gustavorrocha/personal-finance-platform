. "$PSScriptRoot/common.ps1"
Import-LocalConfig
Invoke-Checked uv @('run', '--frozen', 'python', 'scripts/phase0.py', 'migrate')
Invoke-Checked uv @('run', '--frozen', 'python', '-m', 'scripts.validate_bronze')
