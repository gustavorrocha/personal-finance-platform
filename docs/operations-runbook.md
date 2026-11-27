# Synthetic operations and recovery

1. Run `bootstrap.ps1` to install locked dependencies, validate the private directory, restrict ACLs, and generate secrets.
2. Run `run_local.ps1` to start ClickHouse and Ollama, apply SQL migrations, and wait for API and web health.
3. Run `load_synthetic.ps1` to insert two deterministic events. Repeated runs preserve the count.
4. Run `verify_security.ps1` in the default configuration to check network membership, bindings, host ports, health, fake-token log handling, and expected blocked database/AI egress.
5. Run `restore_test.ps1` to restore an encrypted synthetic backup in a disposable ClickHouse container and compare row counts and checksums.
6. Use `docker compose --env-file .env -f infra/compose.yaml down` to stop the default stack while preserving data.

The port scan covers loopback and host IPv4. An unrelated service on a sensitive port fails the check. Investigate the process and verify the firewall, LAN, IPv6, and Docker Desktop or WSL separately when needed.

To recover a lost API health secret, stop the stack, confirm the private directory and its ACL, remove the individual `secrets/api_password` and `secrets/health.xml` files, then rerun bootstrap and recreate the containers. Preserve `keys/backup.key` to restore existing backups. Keep logs, hashes, secret files, and data dumps private.

The API logs event and level. Nginx omits request logs and ClickHouse disables persistent query, text, and trace logs. Diagnose command failures locally.

Migration checksums protect applied SQL files. Run one migrator at a time. If a run stops partway through, rerun the idempotent DDL. The synthetic probe is for validating infrastructure.

For synthetic backups older than seven days, confirm the path and ACL and verify a restore before operator-supervised removal. The lab targets recovery to the last backup and an RTO of up to 15 minutes after Docker is available. RTO is unmeasured. Same-disk backups cannot recover from laptop loss. Before real data, verify BitLocker/WSL, cloud sync exclusions, host protection, retention, independently keyed encrypted backups on a second medium, and a private restore. A production backup workflow belongs to a later phase.

## Phase 1 recovery

On Windows, a verified ClickHouse recovery copy can live in an existing
Docker-managed volume. Put the volume name in `.finance-clickhouse-volume` in
the configured private directory. Use a name beginning with
`personal-finance-clickhouse-`. Both `scripts/run_local.ps1` and
`scripts/clickhouse_gui.ps1` use that external volume when the marker is present.
Preserve the original Windows data directory until recovery is verified. After
the switch it is a point-in-time copy, so keep backing up the active database.

Run `scripts/validate_bronze.ps1` after startup to verify retries, quarantine, and isolated reconstruction. Run capture and warehouse publication with one writer at a time. If ClickHouse is lost, preserve the private Lake, apply the migrations to a fresh instance, and run `finance rebuild-warehouse --from-bronze`. If indexing fails after the manifest is published, retry the capture or replay its UUID once ClickHouse is available. Preserve quarantined evidence for investigation. The foundation backup covers the probe table; `finance export` (below) covers the Lake and the edits.

## Updates and backups

`finance sync-agent` runs the updates, exports and imports requested from the dashboard. `run_local.ps1` restarts it and keeps its PID in `sync-agent.pid` in the private directory; it stops at logoff, and the dashboard badge reports it as off when its heartbeat is older than 90 seconds. It reads Pluggy credentials from the environment or from `secrets/pluggy.env`. The agent, `finance sync`, `market-sync`, `export` and `import` take the same `sync.lock`, so a second writer fails fast with "busy" instead of waiting.

`finance export <file>` writes a zip with the edit tables as Parquet, the raw Lake objects and a manifest with SHA-256 checksums; public market data is left out. The archive is not encrypted: keep it in the private directory or on encrypted media. To recover after losing ClickHouse or the Lake, apply the migrations to a fresh instance and run `finance import <file>`: it writes missing Lake objects create-only, replays the new captures and adds the edit rows that are not there yet. Imports never delete or overwrite, so repeating one is safe. The dashboard accepts archives up to 32 MiB; use the CLI for larger ones.

## Optional ClickHouse GUI

Run `scripts/clickhouse_gui.ps1` after applying the Bronze migrations. Configure the client for HTTP on `127.0.0.1:8123` with user `finance_reader`, database `metadata`, and the password in `secrets/finance-reader.password` under the private directory. The script keeps the password off the console. The proxy is local, and the reader can query synthetic tables and the sources required by their views.

The GUI table browser needs the `database`, `table`, and `data_compressed_bytes` columns in `system.parts` to display storage sizes. Rerun `scripts/clickhouse_gui.ps1` to refresh an existing reader configuration, then reconnect or refresh the table list.

Run `scripts/clickhouse_gui.ps1 -Disable` to remove the proxy and reload ClickHouse without the reader. Disable GUI access before the default port-security test. Changes to the GUI configuration can briefly restart ClickHouse.
