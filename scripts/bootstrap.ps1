param([string]$PrivateDir = (Join-Path $env:LOCALAPPDATA 'PersonalFinancePhase0'))
. "$PSScriptRoot/common.ps1"

foreach ($program in @('uv', 'docker', 'node', 'npm.cmd')) {
    if (-not (Get-Command $program -ErrorAction SilentlyContinue)) { throw "Install $program first." }
}
Invoke-Checked uv @('sync', '--frozen')
Invoke-Checked uv @('run', '--frozen', 'python', 'scripts/phase0.py', 'validate-path', '--private-dir', $PrivateDir)
$PrivateDir = [IO.Path]::GetFullPath($PrivateDir)
$marker = Join-Path $PrivateDir '.finance-phase0'
if (Test-Path -LiteralPath $PrivateDir) {
    if (-not (Test-Path -LiteralPath $marker) -or
        (Get-Content -LiteralPath $marker -Raw).Trim() -ne 'synthetic-only-v1') {
        throw 'Refusing to alter an existing unowned directory. Choose a new -PrivateDir.'
    }
} else {
    New-Item -ItemType Directory -Path $PrivateDir | Out-Null
}
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls.exe $PrivateDir /inheritance:r /grant:r "*${sid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not restrict private directory ACL.' }
$utf8 = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText($marker, 'synthetic-only-v1', $utf8)
foreach ($directory in @('clickhouse', 'clickhouse-logs', 'models', 'secrets', 'keys', 'backups')) {
    New-Item -ItemType Directory -Path (Join-Path $PrivateDir $directory) -Force | Out-Null
}
$random = [Security.Cryptography.RandomNumberGenerator]::Create()
$passwordPath = Join-Path $PrivateDir 'secrets/api_password'
if (-not (Test-Path -LiteralPath $passwordPath)) {
    $bytes = New-Object byte[] 32
    $random.GetBytes($bytes)
    [IO.File]::WriteAllText($passwordPath, ([BitConverter]::ToString($bytes)).Replace('-', '').ToLowerInvariant(), $utf8)
}
$password = [IO.File]::ReadAllText($passwordPath).Trim()
$sha = [Security.Cryptography.SHA256]::Create()
$hash = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($password)))).Replace('-', '').ToLowerInvariant()
$xml = @"
<clickhouse><users><health><password_sha256_hex>$hash</password_sha256_hex><networks><ip>0.0.0.0/0</ip></networks><profile>health</profile><quota>default</quota><grants><query>GRANT SELECT ON metadata.schema_migrations</query></grants></health></users></clickhouse>
"@
[IO.File]::WriteAllText((Join-Path $PrivateDir 'secrets/health.xml'), $xml, $utf8)
$keyPath = Join-Path $PrivateDir 'keys/backup.key'
if (-not (Test-Path -LiteralPath $keyPath)) {
    $bytes = New-Object byte[] 32
    $random.GetBytes($bytes)
    [IO.File]::WriteAllBytes($keyPath, $bytes)
}
$random.Dispose()
$sha.Dispose()
[IO.File]::WriteAllText((Join-Path $script:RepoRoot '.env'), "FINANCE_PRIVATE_DIR=$($PrivateDir.Replace('\', '/'))`n", $utf8)
Import-LocalConfig
Invoke-Checked uv @('run', '--frozen', 'python', '-m', 'scripts.configure_dashboard')
Push-Location apps/web
try { Invoke-Checked npm.cmd @('ci', '--ignore-scripts') } finally { Pop-Location }
Write-Output 'Bootstrap complete. Synthetic data only; no bank credentials required.'
