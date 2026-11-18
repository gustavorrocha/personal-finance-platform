# Implementation plan

The [full implementation plan](plano_financas_datalake_clickhouse.md) records the original version 2.0 specification from November 17, 2026.

Phases 0–2 are merged. Phase 2 provides the [read-only provider coverage audit](provider-coverage.md).
Phase 3 implements [provider ingestion and Silver replay](provider-ingestion.md) on
`feat/incremental-ingestion`. Its acceptance checks use synthetic responses and disposable ClickHouse.
