# Provider ingestion and Silver

Sync uses existing Pluggy application credentials and consented items. Follow
the [coverage runbook](provider-coverage.md) for private environment configuration
and run the redacted audit before the first load. Keep the Lake and ClickHouse
data directory under the private, local storage created by bootstrap. Confirm
disk encryption, an independent backup, and a retention policy before real use.

## Run locally

```powershell
.\scripts\run_local.ps1
uv run --frozen finance sync --full
uv run --frozen finance sync
```

Close the credential-bearing shell when finished. Run one writer at a time.
The first sync for each item reads all available history even without `--full`.
Later incremental syncs read accounts, resources, bills, investments, and
movements again. For existing accounts, transactions use separate reads for new
provider records since the last successful checkpoint minus two days and for
economic dates in the last 45 days. New accounts receive a full transaction read.
The creation filter catches newly delivered, backdated transactions. The
recent-date read picks up changed statuses and reversals within its window.
Use a full sync to review updates outside that window. [Pluggy transaction lifecycle](https://docs.pluggy.ai/en/docs/products/transactions)

The console reports only run UUIDs, states, and record counts. Reported records
are observations, so two page reads can contribute the same logical entity.

| State | Meaning |
|---|---|
| `full`, `incremental` | Bronze and Silver published and the checkpoint advanced |
| `pending` | Connection/resource state published while the item is awaiting action or an update |
| `partial` | Available evidence published while authorization or an expected scope is incomplete |
| `failed` | Collection or replay failed. Use the recovery steps below |

Partial or failed syncs return a nonzero exit code. Pending, partial,
and deletion captures leave the last successful checkpoint unchanged.
An HTTP or pagination failure after a scope has started aborts that item's
capture. A provider refusal before its first page marks the run partial.
Each item is independent. Collection is bounded to 128 response objects or 32 MiB
of expanded JSON per item per run. Capture scale beyond those bounds needs
partitioned full loads.

## Check results and recover

ClickHouse is reached through Docker exec. The optional loopback GUI user retains
its synthetic table grants. Provider payloads, indexes, and Silver rows require
the local operator.

```powershell
docker exec personal-finance-clickhouse-1 clickhouse-client --host 127.0.0.1 --query "SELECT kind, count() FROM metadata.ingestion_publications FINAL GROUP BY kind"
docker exec personal-finance-clickhouse-1 clickhouse-client --host 127.0.0.1 --query "SELECT status, count() FROM core.bank_transaction_current GROUP BY status"
uv run --frozen finance lake verify
```

`metadata.ingestion_run_events` contains started and failed attempts.
If a capture fails before publication, the Lake keeps a sanitized receipt at
`failures/run_id=<uuid>/status.json`. If a committed manifest exists, replay the
given run. If collection failed, retry sync to create a fresh observation.
A lost response from ClickHouse can leave a successful publication behind,
so check the publication and manifest before retrying.

```powershell
uv run --frozen finance replay --run-id <run-uuid>
uv run --frozen finance rebuild-warehouse --from-bronze
```

Run migrations on a replacement ClickHouse instance before a rebuild. Offline
rebuild verifies the manifests and reconstructs the Bronze index, published
observations and checkpoints from the same files. Attempt events for runs without
committed manifests remain operational evidence. A failed run or an integrity
error leaves previously published current rows available for recovery review.

## Reviewed transaction deletions

Archive a trusted Pluggy `transactions/deleted` event privately. Feed its JSON to
the command on stdin and supply its original receipt time as ISO 8601 with an
explicit offset. The command validates the recorded item/account scope and uses
the provider event UUID for idempotency. Reuse the same bytes and receipt time
for a retry.

```powershell
$eventFile = Join-Path $env:FINANCE_PRIVATE_DIR 'deletion-event.json'
Get-Content -Raw -LiteralPath $eventFile |
    uv run --frozen finance apply-deletions --received-at '2026-01-01T12:00:00Z'
```

A tombstone supersedes older observations. Later sightings restore a reappearing
transaction. Ordinary polling preserves previously observed rows that are absent
from a response. Phase 3 receives explicit deletion evidence through this local
import. [Pluggy deletion events](https://docs.pluggy.ai/en/docs/products/transactions)

## Data contracts

Provider manifests use v2. They preserve response bytes and SHA-256 hashes in
the existing manifest-last layout under `bronze/source=pluggy`. The manifest
stores a pseudonymous item key, safe endpoint templates, and pseudonymous
parent scopes for account and investment pages. Full captures mark their lower
reference bound as unbounded using the 1970 sentinel. Incremental reference
dates describe the bounded transaction status recheck. Raw dates, cursor
values, and source identifiers stay in private Bronze.

| Record | Grain and use |
|---|---|
| `metadata.provider_bronze_objects_current` | One exact index row per run and object |
| `metadata.ingestion_publications` | One published event per run, with scope coverage and observation time |
| `metadata.sync_checkpoints_current` | Latest successful collection start and known account scopes per item |
| `core.provider_observations` | Published typed Bronze records, with replay deduplicated using source record identity |
| `core.provider_current` | One latest active version per resource, item, and entity |
| `core.connection_current`, `core.resource_current` | Latest item consent/status and declared resource state |
| `core.institution_observations` | Provider connector identity per observation |
| `core.account_current`, `core.credit_card_current`, `core.balance_observations` | Latest account/card state and historical reported balances |
| `core.bank_transaction_current`, `core.credit_card_bill_current` | Latest transaction and bill details |
| `core.instrument_current`, `core.investment_position_observations`, `core.investment_movement_current` | One provider position identity per item and historical positions, plus current movements per position |

Version order is the UTC collection start or deletion receipt, then run UUID
and record order. Economic dates remain independent of version order. Amounts,
balances, rates and quantities use Decimal with 12 fractional digits and
round-to-nearest, ties-to-even. Keep currency in aggregate checks.
Raw payloads stay in Bronze. A bounded bank description and selected timing,
category, and installment fields are projected to the private localhost
Spending dashboard. Aggregate current views for
exact current counts and totals. Use observations for provenance and history.

Keys are scoped to an existing item and, for transactions, bills and movements,
to the parent account or investment. A reconnection with a new item ID receives
its own full checkpoint and keeps the old history. Review cross-item matches
before combining overlapping histories in portfolio totals. Positions that share
a ticker or instrument label retain their separate provider identities.

## Acceptance results

The full Windows test suite passed 79 tests using synthetic HTTP responses.
The ClickHouse acceptance test used two disposable instances to check exact
counts and totals after repeat sync and replay, unchanged checkpoints after
failed pages and interrupted publication, pending-to-posted transitions,
reviewed tombstones, reconnect scopes, and offline CLI rebuild. The Windows
immutable-write stress check passed 150 competing-write trials. Ruff and
actionlint passed. The GitHub CI run and live Pluggy validation are pending.
