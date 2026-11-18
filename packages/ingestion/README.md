# Ingestion

Phase 1 contains the `finance` local CLI, synthetic capture orchestration and a
reconstructible ClickHouse metadata/synthetic replay adapter. It depends on
`finance-lake`. The Phase 2 `finance audit-coverage` command uses the separate
`finance-pluggy` client for a redacted read of existing consents.

`finance lake list` and `finance lake verify` inspect local files only. Capture,
replay and rebuild register data using Docker exec against the local ClickHouse
container, never an external service. See `docs/data-contracts.md` for exact grains.
