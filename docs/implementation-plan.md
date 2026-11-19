# Implementation plan

The [full implementation plan](plano_financas_datalake_clickhouse.md) records the original version 2.0 specification from November 17, 2026.

Phases 0–3 are merged, including the [read-only provider coverage audit](provider-coverage.md)
and [provider ingestion and Silver replay](provider-ingestion.md).

The [holdings dashboard](holdings.md) displays read-only account and investment
snapshots in English and Brazilian Portuguese. Both use Silver observations and
keep connections separate. The account history API exposes past published balance
observations for one account at a time.

The [private spending slice](spending.md) combines the expense classification work
from Phase 4 with the first dashboard from Phase 5. It uses one ClickHouse spending
view, deterministic classification and a small localhost UI. This slice focuses on
posted expenses, category corrections, and review of ambiguous posted debits.
The [local category suggestions slice](local-classification.md) starts Phase 6
with optional Ollama setup, small batches, a bounded cache and explicit review.
Broader financial modeling, investment performance and scheduling stay in the
longer-term specification.
