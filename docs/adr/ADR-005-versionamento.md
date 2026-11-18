# ADR-005 — Append-only events and deterministic current reads

November 17, 2026. Accepted for Phase 3 onward.

## Context

ReplacingMergeTree resolves duplicate versions eventually, so plain SELECT can return multiple versions.

## Decision

Define monotonic versions per key, break ties by event_id, and document FINAL or argMax reads before creating marts.

## Alternatives

Running OPTIMIZE FINAL daily does not guarantee correct reads.

## Consequences

Financial version models and coexistence tests are scheduled for later phases.
