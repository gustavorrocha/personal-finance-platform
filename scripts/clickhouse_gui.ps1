param([switch]$Disable)
. "$PSScriptRoot/common.ps1"
Import-LocalConfig
$compose = @('compose', '--env-file', '.env', '-f', 'infra/compose.yaml', '-f', 'infra/compose.gui.yaml')
if ($Disable) {
    Invoke-Checked docker ($compose + @('rm', '-s', '-f', 'clickhouse-gui'))
    Invoke-Compose @('up', '-d', '--wait', 'clickhouse', 'api', 'web')
    return
}

$secrets = Join-Path $env:FINANCE_PRIVATE_DIR 'secrets'
$passwordPath = Join-Path $secrets 'finance-reader.password'
$configPath = Join-Path $secrets 'finance-reader.xml'
foreach ($path in @($secrets, $passwordPath, $configPath)) {
    if ((Test-Path -LiteralPath $path) -and
        ((Get-Item -LiteralPath $path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Linked secret paths are forbidden.'
    }
}
$utf8 = New-Object Text.UTF8Encoding($false)
if (-not (Test-Path -LiteralPath $passwordPath)) {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    [IO.File]::WriteAllText($passwordPath, ([BitConverter]::ToString($bytes)).Replace('-', ''), $utf8)
}
$password = [IO.File]::ReadAllText($passwordPath).Trim()
$sha = [Security.Cryptography.SHA256]::Create()
try {
    $hash = ([BitConverter]::ToString($sha.ComputeHash($utf8.GetBytes($password)))).Replace('-', '')
} finally { $sha.Dispose() }
$xml = @"
<clickhouse>
  <profiles><finance_reader><readonly>1</readonly><log_queries>0</log_queries>
    <max_execution_time>10</max_execution_time><max_memory_usage>128000000</max_memory_usage>
  </finance_reader></profiles>
  <users><finance_reader>
    <password_sha256_hex>$hash</password_sha256_hex>
    <networks><ip>0.0.0.0/0</ip></networks>
    <profile>finance_reader</profile><quota>default</quota>
    <grants>
      <query>GRANT SELECT(database, table, data_compressed_bytes) ON system.parts</query>
      <query>GRANT SELECT ON metadata.synthetic_events</query>
      <query>GRANT SELECT ON metadata.bronze_objects</query>
      <query>GRANT SELECT ON metadata.bronze_objects_current</query>
      <query>GRANT SELECT ON metadata.synthetic_bronze_record_versions</query>
      <query>GRANT SELECT ON metadata.synthetic_bronze_publications</query>
      <query>GRANT SELECT ON metadata.synthetic_bronze_records_published</query>
    </grants>
  </finance_reader></users>
</clickhouse>
"@
[IO.File]::WriteAllText($configPath, $xml, $utf8)
Invoke-Checked docker ($compose + @('up', '-d', '--wait', 'clickhouse-gui', 'api', 'web'))
Write-Output 'GUI access is available at http://127.0.0.1:8123 as finance_reader.'
Write-Output 'Copy the password from secrets/finance-reader.password in the private storage folder.'
