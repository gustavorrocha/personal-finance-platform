# ADR-002 — ClickHouse as the only database

November 17, 2026. Accepted in Phase 0.

## Context

Future interactive operations must coexist with OLAP under the single-database constraint.

## Decision

Use ClickHouse databases named core, analytics, and metadata. Keep SQLite, PostgreSQL, and Redis out of the stack.

## Alternatives

An extra transactional database would increase operations and violate scope.

## Consequences

Phase 0 uses a migration ledger and a synthetic table. MergeTree merges do not guarantee transactional uniqueness.
