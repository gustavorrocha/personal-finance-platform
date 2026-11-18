# ADR-006 — Manual events independent of rebuilds

November 17, 2026. Accepted for Phase 4.

## Context

Human corrections must survive mart reconstruction.

## Decision

Capture rules, reviews, and classifications as versioned events with independent backups and read-after-write support.

## Alternatives

Updating cells or editing only Gold would lose traceability.

## Consequences

Define revocation and precedence contracts before adding write endpoints.
