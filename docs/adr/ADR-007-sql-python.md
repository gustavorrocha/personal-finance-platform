# ADR-007 — Analytical SQL and financial Python

November 17, 2026. Accepted for Phases 4 and 8.

## Context

Dimensional modeling and financial calculations have different requirements.

## Decision

Use dbt-clickhouse for modeling and deterministic Python with Decimal for complex metrics.

## Alternatives

Putting all calculations in SQL would complicate testing and missing-data handling.

## Consequences

Install dbt, warehouse clients, and financial libraries when the relevant phase uses them.
