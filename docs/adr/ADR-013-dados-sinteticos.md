# ADR-013 — Public synthetic data and private real data

November 17, 2026. Accepted in Phase 0.

## Context

CI and Git must exclude personal and bank data.

## Decision

Use invented fixtures and keep private runtime directories outside Git and cloud sync.

## Alternatives

Anonymized real statements may still leak or permit reidentification.

## Consequences

Keep private dumps, logs, and volumes out of CI. Enable real data only in its authorized phase.
