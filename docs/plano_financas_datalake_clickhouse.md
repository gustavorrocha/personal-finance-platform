# Implementation plan — Personal finance platform, data lake, and ClickHouse warehouse

**Version:** 2.0 · **Date:** November 17, 2026\
**Status:** Technical plan and roadmap for a coding agent. Production code execution is outside this plan.\
**Initial sources:** Existing connections through Pluggy/Open Finance.\
**Constraints:** ClickHouse is the only database engine. The platform is local-first, inference for real data runs locally, and V1 has no public endpoints. Bronze is durable, with Silver and Gold in ClickHouse.

## 0. Executive summary and decisions

Build a private product unifying accounts, cards, spending, net worth, and investments with auditable history and economic asset classification, including fixed-income ETFs and savings pots.

1. ClickHouse is the only application database. The file lake and model store do not add databases. Keep PostgreSQL and SQLite out of runtime.
2. Bronze persists outside ClickHouse and preserves original files, provenance, and integrity for Silver transformation. The ClickHouse `raw` layer has no canonical role.
3. Silver, Gold, and operational metadata use separate ClickHouse databases named `core`, `analytics`, and `metadata`. Metadata covers checkpoints, rules, events, and tests.
4. Start on an encrypted local filesystem behind `ObjectStore`, with an object-storage-compatible layout. Consider an S3-compatible local backend after the MVP stabilizes or earlier for S3 learning if the interface allows a clean swap. Verify maintenance, support, and hardening before adopting MinIO or another service.
5. Run Ollama inference locally for real data. Optional external LLM comparisons use synthetic data exclusively.
6. Use a CLI and lightweight scheduler in V1. Record future orchestration changes in an ADR. Airflow would add a metastore and increase the attack surface.
7. The integration is read-only. Payments, orders, and financial automation are out of scope.
8. Incorrect financial data is critical. Resolve duplicate versions, report missing returns, and label every estimate.

The pipeline runs from existing Pluggy consents through an isolated HTTPS Python ingestion CLI, compressed immutable files and manifests in Bronze, normalized accounts and investments in Silver, then dbt-clickhouse and Python performance calculations into Gold facts and dimensions. FastAPI serves the private React/TypeScript dashboard. Ollama with a small Qwen3 model suggests classifications for review.

## 1. Product objectives

- **Spending dashboard.** Show expenses by category, subcategory, merchant, card/account, and institution, along with income, cash flow, comparisons, and recurring activity. Recognize card spending by purchase date and model installments and refunds separately. Exclude own-account transfers, card settlements, and investment flows from final spending. Provide manual review, merchant rules, uncategorized transaction detection, and comparison of Pluggy, rule, and LLM categories.
- **Net-worth dashboard.** Show bank balances, card liabilities, investment positions, economic exposure by institution, history, and liquidity. Reconcile products reported both as accounts and investments. Treat ETFs as vehicles and support weighted exposures for hybrid instruments.
- **Performance dashboard.** Show positions, available cost basis, realized and unrealized gains, interest, dividends, coupons, fees, taxes, and computable TWR/XIRR. Use documented CDI and other benchmark sources. Distinguish observed, reconstructed, estimated, and unavailable returns. Check savings-pot coverage and use movements and snapshots. A contracted rate alone cannot establish actual return.
- **Operations and governance.** Track source freshness, connection coverage, quality, Bronze-to-Gold lineage, runs, failures, reprocessing, backups, and restore tests.

Out of scope for the MVP are multiple users, asset-manager portfolio control, money movement, financial advice, public remote access, remote LLM processing of real data, low-latency streaming, and an Iceberg lakehouse.

## 2. Architecture and security boundaries

| Component | Responsibility | Network exposure |
|---|---|---|
| Python `ingestion` | Authenticate to Pluggy, read, write Bronze, register manifests | HTTPS outbound to Pluggy, no public port |
| `bronze_store` | Immutable gzip JSON/JSONL, optional derived Parquet | Restricted local volume, no V1 server |
| ClickHouse | Silver, Gold, metadata | Private Docker network |
| Ephemeral dbt | Build and test models | ClickHouse only |
| Python performance engine | Calculate and record validated financial metrics | No internet by default |
| Ollama | Classify sanitized descriptions | Isolated network, cloud disabled |
| FastAPI | Read Gold, edit rules, classify, show health | Host loopback |
| React | Dashboards and reviews | Host loopback |
| Scheduler | Run incremental CLI and maintenance | No public exposure |

Separate Docker networks into `frontend`, `data`, `ai`, and `egress`. Attach only required services. Consider the host, dual-homed containers, and outbound firewall policy. Leave ClickHouse 8123/9000, Ollama 11434, and Lake ports unpublished by default. Local tools may use an explicitly configured temporary tunnel or loopback binding.

Keep secrets out of Git, images, and logs. Prefer mounted secret files with ACLs and rotation. Grant only necessary Pluggy permissions and never collect bank passwords. Set `OLLAMA_NO_CLOUD=1`, restrict runtime egress, and download models in a controlled setup step. Use BitLocker, LUKS, or FileVault for disks and independent tooling and keys for encrypted backups. Docker does not encrypt volumes. Avoid external analytics, telemetry, and error tracking. GitHub Actions uses synthetic data exclusively.

The threat model covers Pluggy secret theft, laptop loss, host compromise, accidental publication of logs or payloads, malicious dependencies, prompt injection through descriptions, backup leakage, accidental frontend exposure, excessive Docker Desktop/WSL2 privileges, backend RCE, and cross-network access. Record controls, tests, and response procedures for each.

## 3. Bronze data lake

Bronze is the durable landing zone for original Pluggy responses. Keep immutable captures by observation, with extraction metadata and checksums. Derived Parquet is optional and rebuildable. Original JSON is the source of ingestion truth.

```text
private_data/lake/
  bronze/source=pluggy/resource=<resource>/ingestion_date=YYYY-MM-DD/run_id=<uuid>/part-0001.jsonl.gz
  manifests/ingestion_date=YYYY-MM-DD/run_id=<uuid>/manifest.json
  quarantine/run_id=<uuid>/...
  derived/parquet/...   # optional and rebuildable
```

Resources include accounts, transactions, investments, investment movements, and bills. Keep real data outside the Git tree and personal identifiers such as CPF, account number, and full name out of paths. An institution label may appear in a manifest. Apply ACLs to manifests and directory listings.

Provenance includes `run_id`, `object_id`, resource, non-sensitive item alias, UTC retrieval time, endpoint path without query secrets, collector version, reference interval, record count, SHA-256, size, filename, schema fingerprint, consent state, `complete|quarantined` status, and references to previous objects where applicable. The manifest is the commit record.

1. Download and validate the response/pages in memory or protected staging.
2. Write a temporary file, fsync, verify SHA-256, and atomically publish it on the same filesystem.
3. Publish the validated manifest after all objects are durable.
4. Register the run ID, hash, path, and status in `metadata.bronze_objects`.
5. Process Silver with deterministic object and record IDs. Recover between-stage failures with manifest replay and at-least-once, logically idempotent processing.
6. Advance the cursor checkpoint only after durable Bronze and completion of the required stage.
7. Provide `finance lake verify`, `finance lake list`, `finance replay --run-id ...`, and `finance rebuild-warehouse --from-bronze`.

`ObjectStore` provides `put_immutable`, `get`, `list_manifests`, `checksum`, `verify`, and `delete_with_retention_policy`. Start with `LocalObjectStore`. A future `S3ObjectStore` uses a private, versioned, encrypted bucket. Validate maintenance, pinned images, credential policy, and network security before adding local S3-compatible storage. The storage service's internal metadata must not introduce another application SQL database. Integrate derived Parquet through ClickHouse file/object functions when available, keeping transformations independent of the storage endpoint.

## 4. ClickHouse warehouse

Use `core`, `analytics`, and `metadata`. Short-lived landing or staging tables may be rebuilt from the lake.

### 4.1 Silver — core

| Table in core | Grain and key fields | Engine |
|---|---|---|
| institution_observations | connector, institution, observed time | Append MergeTree |
| connection_versions | item/connection, state, version, timestamps | ReplacingMergeTree(version) with exact current view |
| account_versions | account key, type, currency, balance, effective time, version | ReplacingMergeTree(version) |
| bank_transaction_versions | logical transaction key, economic date, Decimal amount, currency, status, deletion, version | ReplacingMergeTree(version) |
| credit_card_bill_versions | bill key, due and statement dates, total, version | ReplacingMergeTree(version) |
| instrument_versions | instrument key, ISIN/CNPJ/ticker, economic terms, version | ReplacingMergeTree(version) |
| investment_position_observations | account, instrument, value date, observation time, quantity, value | Append MergeTree |
| investment_movement_versions | movement key, type, amount, date, version | ReplacingMergeTree(version) |
| balance_observations | account key, economic date, capture time, balance | Append MergeTree |
| asset_exposure_events | instrument, economic class, weight, effective period, source, version | Append MergeTree |
| classification_events | transaction key, category, source, decision, revision/version | Append MergeTree |
| transaction_link_events | logical link among payments, transfers, and investments | Append MergeTree |
| market_data_observations | asset/benchmark, date, value/rate, provider | Append MergeTree |

Document logical grain, effective and observation dates, duplicate handling, and tombstones. Support the same issue across accounts and multiple CDBs with different rates. Identify instruments using more than ticker alone. Use `Decimal` at the appropriate scale for money and rates, `DateTime64(3, 'UTC')` for technical timestamps, `Date` for accounting and economic dates, and `LowCardinality(String)` for appropriate enumerations. Keep customer, account, and transaction identifiers out of text log keys.

### 4.2 Gold — analytics

Dimensions are `dim_date` (calendar and business days when available), `dim_institution` (connector and coverage), `dim_account` (pseudonym, institution, type, currency), `dim_instrument` (vehicle, indexer, liquidity, issuer, maturity), `dim_asset_class` (versioned economic hierarchy), `dim_category` (income/expense taxonomy), and `dim_merchant` (canonical merchant and aliases). Avoid unnecessary personal data and frontend PII.

| Fact | Grain and measures |
|---|---|
| fct_financial_transactions | One current logical transaction with source and nature |
| fct_expenses | One recognized purchase/refund/installment expense under a consistent convention. Exclude own transfers and settlements. |
| fct_cashflow | One economic event with direction, account, and type |
| fct_investment_movements | One reconciled movement |
| fct_positions_daily | Instrument × account × reference date, observation age and observed/carried/estimated status |
| fct_account_balances_daily | Account × date, quality and freshness |
| fct_asset_allocation_daily | Date × economic class × account, with verified ETF weights |
| fct_performance_daily | Portfolio or asset × date, beginning/ending value, flows, result, return, method, quality |
| fct_net_worth_daily | Date × institution/account/component, accounting for liabilities and duplicates |
| fct_data_coverage_daily | Resource × institution × date, completeness, age, flags |

Start with snapshots, versions, and derived `valid_from`/`valid_to`. Consider SCD Type 2 for asset classes, accounts, and instruments when needed. API reads Gold and operational Silver details. Keep raw JSON aggregation out of UI rendering. Views and marts expose completeness and reference dates.

### 4.3 Metadata and auditability

Maintain `bronze_objects`, `ingestion_runs`, `run_events`, `sync_checkpoints_events`, `schema_migrations`, `model_build_runs`, `data_quality_results`, `source_freshness`, `quarantine_events`, `classification_rule_events`, `classification_review_events`, `app_settings_events`, `model_registry`, `reconciliation_events`, `rebuild_runs`, and `backup_manifest_events`. Bronze and user classification, rule, and review events are stateful. Derived Silver, Gold, and projections are rebuildable. Back up non-rebuildable ClickHouse events independently.

### 4.4 Updates

Represent interactive changes as versioned events. Use `FINAL` or deterministic `argMax` grouping for exact current reads because ReplacingMergeTree merges eventually. Use monotonic versions per logical key and an event ID tie-break. Resolve versions before aggregation. Prefer idempotent dbt views or rebuilds initially, then introduce incremental models with documented, tested reconciliation. Guarantee read-after-write for manual corrections using a flushed batch and consistent query. Measure parts. Avoid routine `OPTIMIZE FINAL`.

## 5. Pluggy pipeline and coverage audit

Run `finance audit-coverage` before a full load. Inspect items, connectors, states, resources, accounts, cards, investments, movements, bills, and dates. Check savings-pot and historical data availability per item. Report redacted counts and available-field percentages without balances or sensitive descriptions.

Use `GET /v2/transactions` and preserve the returned opaque `next` query string until it is null. Use endpoint-specific page/pageSize/totalPages pagination for investments, movements, bills, and other applicable endpoints. Reconnected items may change IDs. Use provider identifiers and manual review for ambiguous matches. Recheck recent pending-to-posted transitions, reversals, and deletions. Remote webhooks are outside the MVP. Enforce limits, 429/5xx backoff, timeouts, simple circuit breaking, page counts, and failure manifests.

Sync connections, consents, and institutions first, followed by accounts/balances/cards/bills, then transactions by account and date window, then investment products, positions, and movements. Persist Bronze and manifests, verify and transform Silver, reconcile and classify, build and check Gold, and confirm the checkpoint. Replay uses the lake and persisted events without Pluggy.

## 6. Financial rules

### 6.1 Spending and reconciliation

Keep financial movement nature separate from spending categories. Use `expense`, `income`, `internal_transfer`, `credit_card_settlement`, `investment_contribution`, `investment_redemption`, `tax`, `fee`, `reversal`, and `unknown`. Count purchases once and use card payments to settle liabilities. Match both sides of own transfers using identifiers and time tolerance, preserving ambiguity for review. Treat contributions and redemptions as investment flows. Specify refund, chargeback, installment, revolving-interest, and fee treatment, with a consistent purchase/installment accounting convention. Reconcile cash and savings/investment representations by source link.

### 6.2 Economic classification

Separate `instrument_type` (ETF, CDB, equity, FII, and similar vehicles) from `economic_exposure`. The proposed exposure identifiers are `renda_fixa_pos` for floating-rate fixed income, `renda_fixa_ipca` for inflation-linked fixed income, `renda_fixa_pre` for fixed-rate fixed income, `acoes_br` and `acoes_global` for Brazilian and global equity, `caixa` for cash, and `outros` for other. Use instrument, ISIN, benchmark, or mandate for mapping. Support weights by instrument, economic class, and effective period, with total weight 1 within a configured tolerance. Audit overrides and track `provider|reference|rule|manual` provenance. Verify historical instrument coverage before requiring external prices.

### 6.3 Returns

Calculate realized/unrealized P&L, asset returns, period TWR, eligible XIRR, and benchmark comparisons with Decimal, explicit dates, a deterministic ordering, and currency. TWR requires consistent subperiod valuations and external-flow treatment. XIRR uses dated cash flows and terminal value. Report ambiguous roots, no root, or insufficient signs. Define gross/net conventions for fees, taxes, and dividends. Test transferred positions, amortizations, splits, and contractual fixed-income rates. Reconstruct savings-pot returns from flow-adjusted daily balances when possible and label rate-based estimates. Expose `observed`, `reconstructed`, `estimated`, `partial`, or `unavailable` with `coverage_period`, `missing_days`, `pricing_source`, and `methodology_version`. Use documented and audited CDI/price sources with caching and availability policies.

## 7. Local LLM classification

1. Reconcile and apply deterministic rules first.
2. Keep useful text and strip CPF, account IDs, other personal identifiers, and unnecessary PII.
3. Cache by normalized description, safe context, and model/taxonomy version.
4. Start with local quantized Qwen3 1.7B in Ollama and benchmark CPU/RAM before changing size.
5. Validate closed Pydantic output `category_id`, `requires_review`, and `explanation_short`. Reject unknown categories.
6. Log suggestion and human review events, support revocation, and apply `manual > rule > trusted_provider > llm`.
7. Treat descriptions as untrusted data and test prompt injection.
8. Benchmark on a locally labeled dataset against rules and Pluggy. Track macro-F1, category precision, review rate, latency, RAM, and valid schema rate. Model self-confidence is uncalibrated. Keep real datasets out of CI.
9. Verify that runtime egress cannot reach NVIDIA, OpenRouter, OpenAI, or other remote LLM services.

## 8. dbt, transformation, and quality

Pin compatible dbt-clickhouse versions and test them in CI. Check snapshot and incremental features against ClickHouse behavior. Use `models/staging`, `models/core`, `models/marts`, `tests`, and `seeds`. Use SQL for modeling and tested deterministic Python for complex financial calculations published through Gold/dbt. Validate non-null fields, logical current-key uniqueness, relationships, exposure totals, balance/movement reconciliation, bill deduplication, version state, snapshot quality, and freshness. Specify monetary tolerances and avoid premature rounding. Verify deterministic rebuilds from the same manifests and events. Measure pipeline stage lag, rejected rows, pending classifications, unclassified instruments, days without prices, accepted classifications, and query stability.

## 9. Project structure

```text
personal-finance/
├── README.md
├── docs/           # architecture, threat model, financial methodology, data contracts, runbook, ADRs
├── infra/          # Compose, ClickHouse config.d and users.d, migrations
├── apps/           # api/src, web/src
├── packages/       # pluggy_client, ingestion, lake, domain, reconciliation, classification, performance
├── analytics/     # dbt_project.yml, models/staging, models/core, models/marts, tests, seeds
├── tests/         # fixtures/synthetic, integration, financial, e2e, security
├── scripts/       # bootstrap, run_local, backup, restore_test, load_synthetic (PowerShell)
├── .env.example
├── .gitignore
├── pyproject.toml
└── uv.lock
```

Keep private storage outside Git and cloud sync. Use Python 3.12+, uv, Ruff, Pytest, Pydantic, httpx, clickhouse-connect, dbt-core, dbt-clickhouse, FastAPI, React, TypeScript, TanStack Query, charting, Docker Compose, Ollama, Windows PowerShell, and synthetic-only GitHub Actions.

## 10. CLI and private endpoints

Indicative CLI commands:

```bash
finance doctor
finance audit-coverage --redact
finance sync --resource all
finance sync --resource transactions --item-alias item-1
finance lake verify
finance lake list --run-id <run_id>
finance replay --run-id <run_id>
finance build-silver
finance classify --pending
finance build-gold
finance validate
finance rebuild-warehouse --from-bronze
finance backup
finance restore --verify-only
```

```text
GET  /health
GET  /api/coverage
GET  /api/net-worth?from=&to=
GET  /api/expenses?from=&to=&category=&account=
GET  /api/transactions?status=&page=
POST /api/transactions/{id}/classifications  # append-only event
GET  /api/assets
POST /api/assets/{id}/exposures              # append-only event
GET  /api/positions?date=
GET  /api/performance?from=&to=&method=
GET  /api/pipelines/runs
POST /api/admin/sync                        # localhost and dedicated protection
```

Provide OpenAPI, validation, query limits, restrictive CORS, local bindings, and CSRF protection when using cookies. Keep Pluggy credentials out of the browser. Any future remote access requires a separate ADR for authentication and private access.

## 11. Phases and acceptance criteria

| Phase | Implement | Acceptance |
|---|---|---|
| 0. Local foundation | Monorepo, ADRs, Compose, ClickHouse, Ollama setup without a required model, minimal FastAPI and React, protected volumes, networks, migrations, PowerShell, and synthetic CI | Startup script passes health. Fake secrets stay out of logs. Port checks confirm ClickHouse and Ollama cannot be reached externally. Synthetic backup restores. ClickHouse is the only database. |
| 1. Bronze and storage contract | LocalObjectStore, atomic writes, manifests, hashes, quarantine, verification, bronze_objects index, synthetic API fixtures, offline replay | Retries are logically idempotent. Recover interruptions after files or manifest. Detect corruption by hash. Rebuild from synthetic Bronze. Keep real data outside Git. |
| 2. Pluggy coverage audit | Read-only client, existing items, coverage summary, cursor and page pagination, redacted report | Report resources, counts, coverage windows, and savings-pot status by source. Keep credentials, balances, and transactions out of logs and artifacts. |
| 3. Real ingestion and Silver | Full and incremental sync, immutable Bronze, core versioning, pending states, reconnects, tombstones, and run metadata | Repeated collections/replays preserve counts/totals. Page failure leaves checkpoint unchanged. Exact current reads have no duplicates. |
| 4. Reconciliation, deterministic classification, and financial Gold | Bill and transfer reconciliation, rules, manual events, dimensional expense/cash-flow models and dimensions, dbt tests | Synthetic scenarios balance without double counting spending. Manual edits appear immediately and survive rebuild. |
| 5. Dashboard MVP | FastAPI and React views for spending, net worth, accounts, history, review, freshness, and errors | Synthetic end-to-end and local real-data checks. Filters, cards, and tables reconcile. No unauthorized external access. |
| 6. Local LLM | Isolated Ollama, batch classification, taxonomy, cache, structured validation, benchmarks, and review | Block model egress. Output validates or goes to review. Financial rules stay deterministic. Reproduce benchmark on synthetic data. |
| 7. Instruments and exposures | Instrument enrichment, vehicle and class fields, multi-class rules, ETFs, CDBs, savings pots, Gold allocations, and coverage controls | Weights sum to 100% for each effective period. No duplicate positions or accounts. Keep unclassified assets in totals and flag them for review. |
| 8. Returns and benchmarks | Snapshots, flows, prices/rates, return engine, TWR/XIRR, golden cases, and quality views | Match hand calculations. Flag partial, unavailable, or estimated data. Avoid false precision for savings pots with missing history. |
| 9. Operations, S3, and portfolio demo | Scheduling, incremental backup/restore checks, observability, optional local S3 backend, derived Parquet, benchmarks, and synthetic demo README | Rebuild Silver/Gold from Bronze and restored non-derived events after ClickHouse loss. Recover the Lake from backup. Keep personal data out of Git and public evidence. |

Phases 0 through 5 proceed in order. Phases 6 and 7 can run in parallel after 4. Phase 8 depends on 3, 7, and historical coverage. Phase 9 consolidates operations and the portfolio demo.

## 12. Required tests and metrics

| Scenario | Expected result |
|---|---|
| Crash after JSON write and before manifest | Batch stays uncommitted and recovery is deterministic |
| Modified file | SHA-256 fails and quarantine captures the object |
| Cursor returns multiple pages then null | No lost or duplicated records |
| Sync retry | Same logical keys and totals |
| Coexisting ReplacingMergeTree versions | Gold resolves the latest valid version |
| Card purchase and bill payment | One expense and one settlement |
| Own-account transfer | Zero net income/expense |
| Investment contribution or redemption | Portfolio change with no spending |
| Fixed-income ETF | Fixed-income economic exposure |
| Account/savings-pot duplicate | One economic exposure |
| Contributions on different dates | TWR/XIRR matches methodology and coverage |
| Incomplete flows | Unavailable or partial return |
| Prompt injection in a description | Classifier treats it as data |
| AI container attempts internet access | Connection blocked and expected failure recorded |
| Restore in a clean environment | Data/events reconcile against checksums |

Track freshness, healthy connections, records per resource, critical null rates, failures per 1,000 records, reconciliation differences, classified assets, pending transactions, dashboard p50/p95, rebuild time, and backup verification.

## 13. Backup, retention, and recovery

Encrypt backups of the Lake and non-reproducible ClickHouse state, including rules, classification and review events, and critical metadata. Maintain a full instance backup for fast recovery. Include run ID, checksum, and manifest copies. Automate periodic synthetic restores in isolation and test real restores privately. Define retention and propagate deletions through files and backups. Operational immutability does not imply indefinite retention. Set RPO/RTO and surface stale synchronization after host downtime.

Recover in order: Lake, manual events and essential metadata, Silver, Gold, checksums/counts/balances, then publish the verified version.

## 14. Optional ClickHouse benchmark

Use entirely synthetic datasets of 100k, 1M, 10M, and 100M transactions and snapshots. Compare ORDER BY layouts, partitioning, compression, projections, and materialized views. Measure p50/p95, reads, batch inserts, memory, CPU, FINAL cost, fact rebuild time, and storage scaling. Any cross-database comparison runs as an isolated benchmark. Publish measured methodology and results. PostgreSQL remains outside runtime.

## 15. Decision records

1. ADR-001 — Python/TypeScript monorepo, uv, Ruff, Pytest, and GitHub Actions.
2. ADR-002 — ClickHouse as the only database and tradeoffs for interactive updates.
3. ADR-003 — File-based Bronze, ClickHouse Silver/Gold, and rebuildable state.
4. ADR-004 — LocalObjectStore with a future S3-compatible interface.
5. ADR-005 — Append-only events with deterministic current reads.
6. ADR-006 — Manual events independent of rebuild and versioned classification.
7. ADR-007 — dbt-clickhouse SQL and Python for complex financial calculations.
8. ADR-008 — Read-only Pluggy, endpoint-specific pagination, and a pre-ingestion audit.
9. ADR-009 — Local Ollama, untrusted input, and manual approval.
10. ADR-010 — No Airflow or additional metastore in V1.
11. ADR-011 — Closed networks and encrypted storage/backups.
12. ADR-012 — Performance policy, financial precision, missing data, and economic exposure.
13. ADR-013 — Public synthetic data and private real data.

## 16. Original coding-agent kickoff prompt

> Read the full plan and implement Phase 0 only. Keep Pluggy and banking credentials out of this phase. Deliver a modular Python/uv/Ruff/Pytest monorepo with ClickHouse as the only database, minimal FastAPI and React/TypeScript, private Docker Compose networks, PowerShell scripts, SQL migrations, and synthetic security and infrastructure tests. Write ADRs, a threat model, and a runnable README. Keep sensitive services on localhost, with secrets out of logs. Define LocalObjectStore for Phase 1 persistence. Run tests and lint, document results and remaining work, then stop for Phase 0 acceptance.

## 17. References and things to verify

- [Pluggy cursor and page pagination](https://docs.pluggy.ai/en/reference/basic-concepts)
- [Pluggy transactions, IDs, and reconnects](https://docs.pluggy.ai/en/docs/products/transactions)
- [ClickHouse ReplacingMergeTree and FINAL](https://clickhouse.com/docs/guides/developer/replacing-merge-tree)
- [dbt ClickHouse setup and adapter limitations](https://docs.getdbt.com/docs/local/connect-data-platform/clickhouse-setup)
- [Ollama cloud settings](https://github.com/ollama/ollama/blob/main/docs/faq.mdx)

Verify current documentation, provider availability, adapter versions, and storage options before implementation. Record the versions actually tested.
