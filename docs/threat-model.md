# Threat model

Assets include private secret files, financial data, migration integrity, backups and keys, and the Windows/WSL host. The acceptance environment uses synthetic fixtures. Trust boundaries include the operator to Pluggy, browser to localhost, frontend to API, API to ClickHouse, operator to Docker, container to volume, build to registry, and future provider text to an LLM. The local host user and Docker daemon hold privileged access.

| Threat | Control | Verification | Response |
|---|---|---|---|
| Pluggy credential theft | Private process environment, fixed HTTPS origin, suppressed request logs, and memory-only authentication | Mock transport, cursor-scope and output redaction tests | Revoke with the provider and investigate the host |
| Laptop loss | Disk encryption and independent backup before real data | Manual BitLocker/WSL and restore verification | Revoke secrets and restore from separate media |
| Host compromise | Non-root containers, dropped capabilities, no-new-privileges, ACLs, and no container Docker socket | Configuration tests and host permission review | Stop services, isolate the host, rotate keys |
| Published payloads or logs | Log allowlists, generic errors, excluded secret files, and suppressed query/request logs | Synthetic-token scan and exception tests | Remove publication and revoke exposed secrets |
| Malicious dependencies | Locked builds, minimal dependencies, npm install scripts disabled, synthetic CI | Dependency audits and lockfile review | Block the version, rebuild, and rotate if needed |
| Prompt injection in descriptions | Treat text as untrusted and keep financial tools out of the future classifier | Prompt tests in Phase 6 | Quarantine the suggestion and review the classifier |
| Backup exposure or tampering | AES-256-GCM, separate key file, and checksums | Round trip, wrong key, tampering, and isolated restore | Reject invalid backup and rotate compromised keys |
| Frontend exposure or DNS rebinding | Loopback, TrustedHost, restrictive CORS, CSP | Host/Origin tests and live port inspection | Remove exposure and correct firewall/Compose settings |
| Excess Docker Desktop/WSL privileges | Minimal volumes and no privileged mode, host networking, or Docker socket | Configuration tests and host group/WSL review | Revoke privileges and rebuild containers |
| Backend remote code execution | Read-only image, ledger-only health user, limits | Settings inspection and sanitized failure test | Stop API, rotate its secret, rebuild image |
| Cross-network access | Dedicated AI, data, frontend, and recovery networks | Membership inspection and egress probes | Remove incorrect network membership and review bridges |
| Local denial of service | HTTP/SQL timeouts and memory/PID limits | Configuration tests and HTTP 503 behavior | Stop the offending process and restore availability |
| Corrupted Bronze capture | Manifest-last publication, hashes, sticky quarantine | Crash and corruption tests before replay | Preserve evidence and rebuild from a trusted capture |
| Forged or stale deletion events | Explicit local import, trusted event provenance and receipt time supplied by the operator, known item/account scope, and stable event identity | Synthetic replay and current-state checks | Verify the event archive and rebuild from trusted captures |
| Dashboard rule or review tampering and overbroad reads | Loopback UI with an explicit hostname allowlist, same-origin JSON writes, typed parameters, a restricted service account, and dedicated spending views | Wrong-host, wrong-origin, invalid-category and cross-connection review requests, plus synthetic replay | Shut down the dashboard and inspect the append-only rules and review decisions |
| Optional GUI access | Loopback HTTP bridge, grants for synthetic records and limited part metadata, separate private provider index and Silver tables | Authenticated read, anonymous/default denial, denied writes and unrelated tables | Disable the GUI proxy and remove its reader configuration |

The host can reach private Docker networks and mounted secrets. Local access alone does not identify the caller. Names cannot prove a directory is excluded from synchronization. Docker volumes lack inherent disk encryption. Host administrators and memory capture remain within the privileged boundary.

Docker Desktop permitted frontend external TCP connections despite disabled masquerading. Database and AI external TCP probes were blocked. DNS forwarding and host access remain possible channels. Apply host firewall policy for stronger isolation. The optional GUI bridge allows trusted local clients to reach the database over HTTP. Keep it enabled only while needed.

Same-host synthetic backups exercise encryption and integrity. Disaster recovery needs independent storage and keys. Keep real data, dumps, logs, and private volumes out of CI artifacts. Download models in a controlled Phase 6 setup step.
