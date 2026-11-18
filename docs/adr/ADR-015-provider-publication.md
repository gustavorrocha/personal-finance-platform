# ADR-015 — Provider checkpoints and Silver publication

Status: Accepted for Phase 3

## Context

Pluggy transaction pagination uses transient cursors. A local run can stop after
reading a page, writing Bronze objects, or inserting ClickHouse rows. Current
financial reads and sync checkpoints need a consistent completion boundary.

## Decision

Collect all bounded pages for one existing item and commit a v2 manifest last.
Persist original response bytes with sanitized provenance. Replay verified
manifest records into typed, versioned Silver rows keyed by their Bronze record
identity. Publish one ClickHouse row per successful replay after the inserts.
Current views see only published runs. The checkpoint is derived from the same
publication stream and advances only for full or incremental completion.

Order current versions by observation time and stable intra-run order.
Keep reconnection histories distinct by item. Use the documented provider
deletion event as explicit tombstone evidence and preserve it in Bronze.

## Consequences

Retrying a run or rebuilding on a fresh database reconstructs exact current
state and checkpoints. Queries can resolve current keys without waiting for
physical merges. Private storage holds both the Bronze bytes and their
rebuildable ClickHouse projection. Cross-item reconciliation and long-window
partitioning remain separate work.
