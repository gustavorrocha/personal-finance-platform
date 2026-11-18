# Phase 0 — validation results

## Current result: local runtime checks passed

Verified on 17 November 2026 after fixing tmpfs parsing and localhost port publishing.
This section supersedes the earlier historical snapshots below. Phase 1 has not started.

| Check | Observed result |
|---|---|
| `run_local.ps1` | Passed; all four services healthy and Windows localhost health reachable |
| API and web image builds | Passed with frozen dependencies |
| `load_synthetic.ps1` run twice | Passed; exactly 2 rows and Decimal total 10.00 verified |
| `verify_security.ps1` | Passed: active bindings restricted to 127.0.0.1, no published ClickHouse/Ollama ports, synthetic token absent from logs |
| Database and AI external TCP probes | Blocked in each real container network namespace |
| `restore_test.ps1` | Passed; AES-GCM backup restored into an independent tmpfs ClickHouse instance; row count and ordered row checksum match |
| Python tests | 17 passed, none skipped; existing Starlette/httpx deprecation warning |
| Ruff lint and formatting | Passed |
| Frontend tests/build/audits | Passed in the earlier unchanged frontend verification |

The initial internal-only frontend bridge left requested port bindings inactive on this
Docker engine. The frontend now uses a private bridge with explicit loopback publication,
default host binding 127.0.0.1 and outbound IP masquerading disabled. Data, AI, recovery and
reserved egress networks remain internal. Runtime verification now checks active mappings,
not only the requested HostConfig bindings.

**Measured limitation:** Docker Desktop still allows API/web external TCP connections despite
the no-masquerade setting. It is not an outbound firewall. Database and Ollama external TCP
connections were blocked. These results do not prove DNS isolation, every destination/port,
IPv6 protection or resistance to a compromised Docker host. Use host firewall policy if
frontend egress must be denied; do not describe the whole stack as air-gapped.
Reference: [Docker bridge network options](https://docs.docker.com/engine/network/drivers/bridge/).

The stack remains running at `http://127.0.0.1:8080` and the API at
`http://127.0.0.1:8000/health`. No original data volume was removed. The restore container
was removed after verification; encrypted synthetic backup artifacts remain in private storage.

Still outside this session's verification: GitHub CI execution, visual browser inspection,
an independent LAN/IPv6 port scan, image vulnerability scanning, and manual BitLocker/WSL
and disaster-recovery checks. There is no production backup or real-data authorization.
Stop here for evaluation of the Phase 0 acceptance criteria.

Suggested follow-up commit: `fix: restore localhost publishing while isolating database and AI services`.

## Initial verification

The original workspace contained the implementation plan. The repository was initialized locally. The first commit attempt hit a permission error at `.git/index.lock` and left the files in the workspace. Later commits and the foundation CI fix were published separately.

| Check | Initial result |
|---|---|
| `uv lock` and `uv sync --frozen` | API and Lake workspace installed |
| `uv run --frozen pytest -q` | 17 passed, none skipped after the mount fix |
| Ruff lint and format | Passed |
| `npm ci --ignore-scripts` | Passed with the lockfile |
| Frontend lint and tests | TypeScript and Prettier passed, plus three tests |
| Frontend build and npm audit | Build passed, final audit reported zero vulnerabilities |
| pip-audit against the uv export | No known vulnerabilities reported |
| Compose validation and PowerShell parsing | Passed |
| Static security and encryption checks | Loopback, internal networks, non-root, resource limits, file secrets, round trip, tampering, and wrong-key checks passed |

Tested versions included Python 3.12.8, uv 0.11.6, Node 24.19.0, npm 11.17.0, Ruff 0.17.5, Pytest 9.2.0, FastAPI 0.163.2, httpx 0.28.1, cryptography 50.0.2, and esbuild 0.28.2. Lockfiles identify exact transitive releases. Starlette TestClient reported an httpx deprecation. pip-audit flagged an export without hashes with `--no-deps`. The audited list came from the frozen uv resolution and enumerated transitive packages. The `pluggy` entry in uv.lock belongs to Pytest. Sandbox npm commands run together initially hit `spawn EPERM`. Separate test and build runs passed.

The initial npm audit flagged transitive ReDoS in picomatch without a published fix in the checked version. The build moved from Vite to esbuild. Final versions also resolved the esbuild and cryptography advisories without a forced npm audit fix.

The initial Docker engine connection returned permission denied on `dockerDesktopLinuxEngine`. Runtime validation awaited operator bootstrap and engine access. Static Compose checks and mocked API tests established configuration and behavior separately from live SQL and networking. The runtime results above supersede that initial blocker.

```powershell
.\scripts\bootstrap.ps1
.\scripts\check.ps1
.\scripts\run_local.ps1
.\scripts\load_synthetic.ps1
.\scripts\load_synthetic.ps1
.\scripts\verify_security.ps1
.\scripts\restore_test.ps1
```

The verifier expects two events totaling Decimal 10.00, healthy localhost endpoints, no sensitive host bindings, and blocked external AI connections. The restore uses a separate tmpfs instance. Foundation work covers synthetic data and the original probe, with real data, full production backups, and financial models scheduled separately.

## Follow-up: Docker tmpfs mount parsing

The operator successfully ran `bootstrap.ps1` and downloaded the ClickHouse and Ollama
images. Stack startup then failed with `invalid mount path: 'noexec'`.

Root cause: the unquoted YAML flow-list entries for API, web and Ollama split each tmpfs
mount at its option commas. Docker received `noexec`, `nosuid` and `size=...` as separate
mount paths. Each complete mount string is now quoted; all security options are retained.
The restore service already used block-list strings and did not need a change.

A regression test reproduced the split (four list items instead of one) before the fix.
After the fix, all 17 Python tests, Ruff checks, format checks and Compose configuration
validation passed. `run_local.ps1` was retried with operator authorization, but this agent
session still received `permission denied` on `dockerDesktopLinuxEngine` before startup.
Runtime health, port/egress/log checks and isolated restore therefore remain pending.

Suggested commit: `fix: preserve tmpfs mount options in Docker Compose`.
