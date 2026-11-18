# Local architecture

The web service calls FastAPI, which reads ClickHouse. Ollama is isolated and runs without a model in the foundation stack. The host CLI handles synthetic ingestion and replay. Scheduling and dbt are planned for later phases.

| Network | Services | Boundary |
|---|---|---|
| frontend | api, web | Private bridge with explicit loopback publishing and masquerading disabled |
| data | api, clickhouse | Internal network. The API health user can read only the migration ledger. |
| ai | ollama | Internal network without runtime clients in the foundation |
| egress | none | Reserved and closed |
| recovery | temporary restore container | Isolated ClickHouse in tmpfs |
| gui | optional clickhouse-gui proxy | Loopback HTTP on 8123, with scoped reader authentication |

The web and API publish only on `127.0.0.1`, on ports 8080 and 8000. The default configuration leaves ClickHouse and Ollama ports unpublished. The optional GUI proxy joins the data network and forwards HTTP only. The database container remains on the internal data network. Services use non-root accounts, dropped capabilities, and memory and process limits. Private bind mounts live outside Git and cloud sync under host ACLs.

The publishing bridge permits host loopback access. On the tested Docker Desktop version, API and web still had external TCP access with masquerading disabled. Host firewall policy governs stronger egress isolation. Internal ClickHouse and Ollama egress probes were blocked.

The uv workspace contains the API, Lake, and ingestion packages. The frontend has a separate npm lockfile. SQL migrations create `core`, `analytics`, and `metadata`, a migration ledger, and synthetic tables and views. Migrations run serially, are checksum tracked, and use additive or compensating changes.

The operator CLI writes Bronze outside the repository. The API has no Lake mount. Captures publish a manifest after durable gzip objects. ClickHouse indexes can be rebuilt from the Lake. Replay verifies the capture, stages a generation, and publishes a final event. See [data contracts](data-contracts.md) and [ADR-014](adr/ADR-014-bronze-replay-publication.md).

References consulted November 17, 2026 include [Compose networking](https://docs.docker.com/compose/how-tos/networking/), [ClickHouse Docker](https://clickhouse.com/docs/install/docker), [ClickHouse backup](https://clickhouse.com/docs/operations/backup), [FastAPI Docker](https://fastapi.tiangolo.com/deployment/docker/), and the [Ollama FAQ](https://github.com/ollama/ollama/blob/main/docs/faq.mdx). Images use full version tags. Validate image digests and runtime behavior during acceptance.
