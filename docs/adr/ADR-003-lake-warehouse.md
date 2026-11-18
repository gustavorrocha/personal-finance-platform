# ADR-003 — External Bronze and a rebuildable warehouse

November 17, 2026. Accepted and implemented for synthetic Phase 1.

## Context

Preserve original evidence independently of the lifetime of the warehouse.

## Decision

Store Bronze in files, Silver in core, and Gold in analytics. Preserve manual events independently.

## Alternatives

Canonical raw data solely in ClickHouse would prevent external replay after warehouse loss.

## Consequences

Future backups must cover the Lake and non-rebuildable events.
