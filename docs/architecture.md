# Arquitetura da Fase 0

`web → api → ClickHouse`. Ollama está pronto, sem modelo, separado dos demais serviços.
Não há serviços de ingestão, dbt ou agendamento em execução.

| Network | Services | Boundary |
|---|---|---|
| frontend | web, api | Private bridge; localhost publishing; outbound masquerading disabled |
| data | api, clickhouse | Usuário health pode ler somente schema_migrations |
| ai | ollama | Inferência sem egress e sem clientes nesta fase |
| egress | nenhum | Reservada e fechada; abertura futura requer revisão |
| recovery | restore efêmero | Base limpa em tmpfs sem acesso à base original |

Somente API (`127.0.0.1:8000`) e web (`127.0.0.1:8080`) publicam portas.
ClickHouse e Ollama não possuem mapeamentos. API é dual-homed e não fornece proxy genérico.
Todos os processos são non-root, sem capabilities, com limites de memória/PIDs.
Volumes bind ficam em raiz privada com ACL, externa ao Git e sincronização na nuvem.

The frontend bridge is deliberately not `internal: true`: internal-only endpoints suppressed
host port publication on the tested Docker engine. The data/AI/recovery networks remain
internal. Disabling IP masquerading is defense in depth, not an egress firewall: live probes
on Docker Desktop found API/web could still reach an external TCP address. ClickHouse and
Ollama probes were blocked. Host firewall policy is required for stronger frontend egress
restrictions; only synthetic data is permitted here.

Workspace uv: `finance-api` e `finance-lake`; fronteiras futuras ficam documentadas,
sem instalar bibliotecas de integrações que não são usadas. Frontend tem lock npm independente.
SQL cria somente `core`, `analytics`, `metadata`, ledger e tabela sintética de infraestrutura.
A migração é idempotente, com checksum e execução por operador único, antes da API.
Não há rollback destrutivo: para reverter uma mudança futura, adicionar migração compensatória.

O contrato de Lake é abstrato: nenhuma escrita Bronze, manifesto, hash de objeto real ou replay
foi implementado. Não há S3/MinIO nem segundo SGBD. Metadados financeiros também ficam para as
respectivas fases. Retornos e valores monetários não são calculados na Fase 0.

Referências consultadas em 17/11/2026:
[redes Compose](https://docs.docker.com/compose/how-tos/networking/),
[ClickHouse Docker](https://clickhouse.com/docs/install/docker),
[backup ClickHouse](https://clickhouse.com/docs/operations/backup),
[FastAPI Docker](https://fastapi.tiangolo.com/deployment/docker/),
[Ollama FAQ](https://github.com/ollama/ollama/blob/main/docs/faq.mdx).
Imagens têm tags de versão completa; validar execução e digests no aceite Docker.
