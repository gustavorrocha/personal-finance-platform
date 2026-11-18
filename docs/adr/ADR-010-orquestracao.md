# ADR-010 — Lightweight local orchestration

November 17, 2026. Accepted in Phase 0.

## Context

Heavy orchestration adds dependencies and an extra metastore.

## Decision

Use PowerShell and a local CLI for V1. Add lightweight scheduling in the operations phase.

## Alternatives

Airflow, queues, and auxiliary databases add attack surface without a current need.

## Consequences

Stop commands on failure. Scheduling and financial automation are outside the current scope.
