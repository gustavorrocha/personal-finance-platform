# Personal Finance Platform

This local workspace uses ClickHouse as its only database. It supports synthetic
validation and optional sync of existing Pluggy connections into immutable Bronze
captures and typed Silver views. The localhost dashboard shows monthly spending and
lets you correct local merchant categories.

## Try the spending dashboard

After bootstrap, run these commands in the same PowerShell session:

```powershell
.\scripts\run_local.ps1
uv run --frozen finance demo-spending
Start-Process http://127.0.0.1:8080
```

Select **Synthetic demo** if you have multiple connections. November 2026 shows
**BRL 257.03** across seven posted entries. Change the category of one West Market
row to check that all three matching entries update. The demo uses invented data and
requires no Pluggy credentials. See the [spending runbook](docs/spending.md).

## Run on Windows

Use PowerShell 5.1+, Python 3.12, uv 0.11.6, Node 24, npm 11.17.0, and Docker Desktop
with the Linux engine and Compose v2+. Allocate at least 6 GB to Docker and run from a
regular PowerShell session at the repository root.

```powershell
.\scripts\bootstrap.ps1
.\scripts\check.ps1
.\scripts\run_local.ps1
Invoke-RestMethod http://127.0.0.1:8000/health
Start-Process http://127.0.0.1:8080
```

Bootstrap defaults to `%LOCALAPPDATA%\PersonalFinancePhase0` and grants access to the
current user and SYSTEM. To choose another location, pass `-PrivateDir C:\finance-phase0`.
Use private local storage outside Git and cloud sync. Bootstrap refuses preexisting
directories without its ownership marker. The local `.env` stores the path, and generated
secrets live in separate private files.

The startup script starts ClickHouse and Ollama, applies checksum-tracked migrations,
and starts the API and frontend. The API reports foundation health at
`http://127.0.0.1:8000/health` and serves its schema at `/openapi.json`.
The frontend serves the localhost spending dashboard. ClickHouse and Ollama use internal networks.
See the [foundation validation report](docs/phase-0-results.md) for the measured Docker
Desktop frontend egress behavior.

## Validate and replay Bronze

With the stack running, execute the acceptance script and inspect the fixture capture.

```powershell
.\scripts\validate_bronze.ps1
uv run --frozen finance lake list
uv run --frozen finance lake verify
uv run --frozen finance lake ingest-synthetic --fixtures tests/fixtures/synthetic
uv run --frozen finance replay --run-id 11111111-1111-4111-8111-111111111111
uv run --frozen finance rebuild-warehouse --from-bronze
```

The validation script loads `FINANCE_PRIVATE_DIR` into the current shell. The CLI uses
that directory's `lake` child. To select a different private path, put
`--root <absolute-private-path>` before the subcommand.

The fixtures produce one run, two compressed response objects, and three replay records.
Retry the same capture with the same UUID, timestamp, and bytes. Assign a new UUID for a
new observation. Filesystem listing and verification run offline. Capture registration,
warehouse replay, and rebuild use Docker exec against local ClickHouse.

Read synthetic state through `metadata.bronze_objects_current` and
`metadata.synthetic_bronze_records_published`. Run warehouse writers serially. The synthetic
rebuild publishes a complete generation after validation. The acceptance script also rebuilds
into an independent temporary ClickHouse instance and checks that corruption cannot replace
published rows.

See [Phase 1 results](docs/phase-1-results.md), [data contracts](docs/data-contracts.md),
and [the publication decision](docs/adr/ADR-014-bronze-replay-publication.md).

## Audit provider coverage

Phase 2 adds `uv run --frozen finance audit-coverage --redact` for existing Pluggy
connections. See the [coverage runbook](docs/provider-coverage.md)
for local credential configuration and how to interpret the redacted report.

## Sync and verify Silver

Run the synthetic integration check against disposable ClickHouse using the local Compose
configuration created during bootstrap.

```powershell
$env:FINANCE_TEST_CLICKHOUSE = '1'
uv run --frozen pytest -q tests/test_provider_ingestion.py
Remove-Item Env:\FINANCE_TEST_CLICKHOUSE
```

The [provider ingestion runbook](docs/provider-ingestion.md) covers first and incremental
syncs, local aggregate checks, failure recovery, and applying reviewed deletion events.

## Foundation checks and shutdown

For a local database GUI, run `scripts/clickhouse_gui.ps1` and connect over HTTP to
`127.0.0.1:8123` with user `finance_reader`, database `metadata`, and the password
in `secrets/finance-reader.password` under the private storage directory.
See the [GUI runbook](docs/operations-runbook.md#optional-clickhouse-gui) to disable access.

```powershell
.\scripts\load_synthetic.ps1
.\scripts\verify_security.ps1
.\scripts\backup.ps1
.\scripts\restore_test.ps1
docker compose --env-file .env -f infra/compose.yaml down
```

The foundation backup seals the `metadata.synthetic_events` probe table in an AES-256-GCM
envelope. Backup files are in the private `backups` directory and the key is in
`keys/backup.key`. The restore check uses an independent container and compares ordered rows.
The Lake needs an independent backup before real-data use.

| Path | Responsibility |
|---|---|
| `apps/api`, `apps/web` | FastAPI health endpoint and static React frontend |
| `packages/lake` | ObjectStore, local backend, manifests, and file replay |
| `packages/ingestion` | Local CLI, provider collection, ClickHouse indexing and Silver replay |
| `infra`, `scripts` | Compose, SQL migrations, and operator commands |
| `tests`, `.github/workflows/ci.yml` | Synthetic tests and CI |

Dependency versions are locked in `uv.lock` and `apps/web/package-lock.json`.
Use `scripts/check.ps1` for lint, tests, the frontend build, and its dependency audit.
Start the container API through Compose. For a manual Uvicorn run on the host, bind
it to `127.0.0.1`.

See the [implementation plan](docs/implementation-plan.md), [operations runbook](docs/operations-runbook.md),
[threat model](docs/threat-model.md), and [ADRs](docs/adr/README.md). Acceptance tests use
synthetic data. Disk encryption, independent backups, and an approved retention policy
are operational prerequisites for real data.
