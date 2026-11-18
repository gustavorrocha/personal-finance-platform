# Ingestion

Phase 1 contains the `finance` local CLI, synthetic capture orchestration and a
reconstructible ClickHouse metadata/synthetic replay adapter. It depends on
`finance-lake`; no provider SDK, remote endpoint or financial model is included.

`finance lake list` and `finance lake verify` inspect local files only. Capture,
replay and rebuild register data using Docker exec against the local ClickHouse
container, never an external service. See `docs/data-contracts.md` for exact grains.
