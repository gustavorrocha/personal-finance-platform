# ADR-004: Local object storage with immutable publication

Date: 17 November 2026. Status: implemented for synthetic Phase 1 evaluation.

## Context

Bronze needs original response bytes and a filesystem implementation that can later
be replaced by an object-store adapter without changing capture/replay semantics.

## Decision

Keep the abstract `ObjectStore` boundary and implement `LocalObjectStore` with the
standard library. Write a same-directory temporary file, flush and fsync it, verify
its SHA-256, and atomically publish without overwriting an existing destination.
Windows uses rename, which refuses existing destinations; POSIX uses hard-link
publication plus temporary-file unlink to avoid overwrite races. POSIX parent
directories are fsynced. Identical retries succeed; conflicting bytes fail.

The root must be private, local, outside Git/cloud sync, and carry an ownership
marker. Existing unowned directories, traversal, alternate data streams, symlinks
and Windows junctions are rejected. Host administrators remain trusted; these
checks do not defeat a same-user attacker racing filesystem operations.

## Alternatives

MinIO/S3 adds a service outside this phase. `os.replace` could silently destroy
an immutable object, so it is not used for publication.

## Consequences

Process-death tests cover both sides of manifest publication. Windows does not
expose portable directory fsync; abrupt power-loss behavior on the actual NTFS
device has not been certified. Deletion fails closed until an approved retention
policy includes referenced backups. No S3 implementation or automatic cleanup is added.
