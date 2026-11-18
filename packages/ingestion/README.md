# Ingestion

The `finance` CLI uses `finance-lake` for immutable capture and replay and
`finance-pluggy` for redacted audits and collection from existing consents.

`finance lake list` and `finance lake verify` inspect local files. Replay and rebuild
use local files and ClickHouse through Docker exec. See the
[provider ingestion runbook](../../docs/provider-ingestion.md) for grains and recovery.
