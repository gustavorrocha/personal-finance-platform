. "$PSScriptRoot/common.ps1"
Invoke-Checked uv @('sync', '--frozen')
Invoke-Checked uv @('run', '--frozen', 'ruff', 'check', '.')
Invoke-Checked uv @('run', '--frozen', 'ruff', 'format', '--check', '.')
Invoke-Checked uv @('run', '--frozen', 'pytest', '-q')
Push-Location apps/web
try {
    Invoke-Checked npm.cmd @('ci', '--ignore-scripts')
    Invoke-Checked npm.cmd @('run', 'lint')
    Invoke-Checked npm.cmd @('test')
    Invoke-Checked npm.cmd @('run', 'build')
    Invoke-Checked npm.cmd @('audit', '--audit-level=high')
} finally { Pop-Location }
