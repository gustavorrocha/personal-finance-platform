# ADR-014: Manifest-last captures and append-only replay publication

Date: 17 November 2026. Status: implemented for synthetic Phase 1 evaluation.

## Context

Files and ClickHouse cannot share a transaction. A crash must not publish a
partial capture, and losing ClickHouse must not lose the original evidence.
The tested Docker Desktop Windows bind mount rejects `renameat2`, including
ClickHouse `EXCHANGE TABLES` and `CREATE OR REPLACE VIEW` publication.

## Decision

Publish the immutable manifest only after all gzip response objects are durable.
Register the capture in ClickHouse afterward; a metadata failure leaves a committed
manifest available for recovery. Retry the same run ID and capture metadata to
recover orphan objects or reconstruct the index without a provider connection.

Quarantine is append-only and sticky: preserve evidence, write a run status marker,
and reject replay. The metadata index gives quarantined status version 2 precedence
over complete status version 1. Consumers must use the exact `FINAL` current view.

Rebuild synthetic rows under a new build UUID. Only after all manifests/objects
validate and all rows are inserted, append a publication event. The published view
selects that complete build using `argMax(build_id, (version, publication_id))`.
Partial builds remain invisible. Run-level replay copies other published runs into
the new generation, then adds the selected run and publishes last.

## Alternatives

Direct truncation would expose partial or empty results on failure. Filesystem
table exchange is unavailable on the tested volume. Neither another database nor
a generic distributed transaction framework is needed for this local workflow.

## Consequences

Capture/rebuild orchestration is single-writer. Individual immutable file writes
are race-tested, but concurrent warehouse publishers are not supported. Previous
builds and orphan files remain until a reviewed retention/backup policy exists.
SHA-256 detects corruption against a trusted manifest, not a privileged attacker
who rewrites both data and provenance. Only synthetic replay tables exist here;
financial Silver/Gold transformations remain in their planned phases.
