# ADR-011 — Closed networks and protected storage

November 17, 2026. Accepted in Phase 0.

## Context

The repository may live in OneDrive. Keep volumes, logs, and credentials in private storage.

## Decision

Use loopback bindings, unpublished database and AI ports by default, externally mounted secrets with ACLs, and AES-GCM for synthetic backups. The optional GUI bridge forwards localhost HTTP to ClickHouse for a scoped read-only account.

## Alternatives

Docker volumes and localhost alone cannot provide disk encryption or authenticate host processes.

## Consequences

The host is privileged. Validate BitLocker/WSL, firewall behavior, and independent backup before handling real data. On the tested Docker Desktop host the frontend retained outbound TCP access despite disabled masquerading. The verifier checks live loopback mappings and blocked database/AI egress in the default configuration.
