# Phase 1 — implementation and validation

The Bronze implementation was committed locally on `feat/bronze-storage` as `800c2f9`.
Hosted CI for Phase 1 awaits publication. Provider access belongs to Phase 2.

## Delivered

- Immutable private `LocalObjectStore` with atomic publication, checksums,
  ownership/path validation and fail-closed retention deletion.
- Canonical manifest-last gzip captures preserving original synthetic response
  bytes and their provenance. Idempotent retries reuse the same capture identity.
- Quarantine evidence and sticky run state; corruption prevents any replay rows.
- `finance` CLI for local listing/verification, synthetic capture, replay and
  warehouse rebuild, with sanitized argument/operation errors.
- Additive ClickHouse metadata/index migrations and exact current/published views.
- Single-writer append-only rebuild generations with a final publication event.
- PowerShell validation and a synthetic CI step covering clean-instance recovery.

## Observed checks

The live Windows/Docker validation passed capture retries, repeated index/replay,
rebuild equality and reconstruction in an independent ClickHouse instance in tmpfs.
A damaged capture was quarantined and indexed as such; published rows stayed unchanged.
The temporary recovery container was removed after the test.

Expected fixture state: one committed run, two objects and three replay records.
Ordered replay SHA-256 observed:
`976cf68d5f5bcaff565bceda840fb26ea254d8829602cbc7e3093a66eaac412f`.

The unit/security suite additionally tests real subprocess death immediately
before/after manifest publication, network-free file replay, conflicting concurrent
file writes, traversal/Windows junctions, malformed input and suppressed error values.
The final suite passed all 60 tests on Windows and in a disposable Linux container.
Ruff lint and formatting, actionlint, and `git diff --check` passed. Pytest reported
the existing Starlette TestClient deprecation warning on both platforms.

## Filesystem finding

`EXCHANGE TABLES` and `CREATE OR REPLACE VIEW` failed on this Windows bind mount
with `renameat2() is not supported`. The implemented publication protocol therefore
appends build rows and a publication pointer; it does not rely on filesystem table
exchange or direct truncation. See ADR-014.

## Boundaries and pending checks

- Only synthetic fixtures and local ClickHouse are supported; real Silver/Gold,
  provider coverage and remote integrations remain in their later phases.
- The updated hosted CI has not run: committing/pushing requires explicit approval.
- Windows file fsync/process-death tests do not certify hardware power-loss durability.
  Private ACL/BitLocker/WSL verification and an independent encrypted Lake backup
  remain operational prerequisites before real data.
- Automated deletion, orphan cleanup and prior-build retention are deliberately
  disabled until the retention policy includes backups and live references.
- The Phase 0 Docker Desktop frontend egress limitation still applies. Database/AI
  must remain internal; no new service or published port is added.
- Stop after Phase 1 evaluation; do not access the provider or advance automatically.
