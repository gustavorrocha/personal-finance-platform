# Implementation plan

The [full implementation plan](plano_financas_datalake_clickhouse.md) records the original version 2.0 specification from November 17, 2026.

Phases 0–3 are merged, including the [read-only provider coverage audit](provider-coverage.md)
and [provider ingestion and Silver replay](provider-ingestion.md).

The [holdings dashboard](holdings.md) starts with a read-only account snapshot.
It builds on the current Silver account observations and keeps connection scopes
separate for the later dashboard and investment views.

The [private spending slice](spending.md) combines the expense classification work
from Phase 4 with the first dashboard from Phase 5. It uses one ClickHouse spending
view, deterministic classification and a small localhost UI. This slice focuses on
posted expenses, category corrections, and review of ambiguous posted debits.
The [local category suggestions slice](local-classification.md) starts Phase 6
with optional Ollama setup, small batches, a bounded cache and explicit review.
Broader financial modeling, investments and scheduling stay in the longer-term
specification.
