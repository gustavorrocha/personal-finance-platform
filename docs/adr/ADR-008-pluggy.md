# ADR-008 — Read-only integration and pre-ingestion audit

November 17, 2026. Accepted for Phase 2.

## Context

Verify actual resource coverage and pagination before ingestion.

## Decision

Use read-only connections, opaque transaction cursors, and endpoint-specific pagination. Keep bank credentials out of the integration.

## Alternatives

Assuming coverage or implementing payments would conflict with the plan.

## Consequences

Phase 2 introduces the provider client and coverage audit.
