# ADR-012 — Financial precision and missing information

November 17, 2026. Accepted for later financial phases.

## Context

Incorrect financial results are critical.

## Decision

Use Decimal for money, distinguish economic dates from UTC timestamps, and expose quality. Track economic exposure separately from ETF vehicle type.

## Alternatives

Floating-point money, invented returns, and aggregation across versions produce misleading results.

## Consequences

Phase 0 exercises Decimal in a fixture. Returns, exposure, and reconciliation are later deliverables.
