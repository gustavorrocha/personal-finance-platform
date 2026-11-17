# Finanças pessoais — Fase 0

Monorepo local para avaliação da infraestrutura, exclusivamente com dados sintéticos.
ClickHouse é o único SGBD. Não há conexão com bancos ou Pluggy, ingestão, classificação,
modelo LLM, dashboards financeiros ou persistência Bronze nesta entrega.

## Executar no Windows

Pré-requisitos: PowerShell 5.1+, Python 3.12, uv 0.11.6, Node 24, npm 11.17.0,
Docker Desktop com engine Linux acessível e Compose v2+.
Disponibilize pelo menos 6 GB para o Docker. Não execute em um shell elevado.

Na raiz do repositório:

```powershell
.\scripts\bootstrap.ps1
.\scripts\check.ps1
.\scripts\run_local.ps1
Invoke-RestMethod http://127.0.0.1:8000/health
Start-Process http://127.0.0.1:8080
```

O bootstrap usa `%LOCALAPPDATA%\PersonalFinancePhase0`, fora do repositório e do OneDrive,
com ACL para o usuário atual e SYSTEM. Pode-se informar `-PrivateDir C:\finance-phase0`.
Uma pasta preexistente sem marcador é recusada. `.env` guarda somente o caminho;
segredos aleatórios são arquivos externos e não são exibidos. Não forneça credenciais bancárias.
Installations download packages and images. Database/AI use internal networks; the publishing
frontend uses a private bridge with loopback bindings and outbound masquerading disabled.
On Docker Desktop this setting does not block frontend egress; see the measured limitations
in `docs/phase-0-results.md`.

`run_local.ps1` inicia ClickHouse/Ollama, aplica a migração por checksum, depois sobe API/web.
`/health` retorna `{"status":"ok","phase":0}` apenas após consultar o registro de migração
com usuário de leitura restrito. A indisponibilidade retorna 503 sem detalhes internos.
OpenAPI: `http://127.0.0.1:8000/openapi.json`. Não há endpoints de escrita.

```powershell
.\scripts\load_synthetic.ps1
.\scripts\load_synthetic.ps1  # idempotência da fixture
.\scripts\backup.ps1
.\scripts\restore_test.ps1
.\scripts\verify_security.ps1
docker compose --env-file .env -f infra/compose.yaml down
```

O backup cobre **somente `metadata.synthetic_events`**: formato Native do ClickHouse,
manifesto com hashes/contagem, envelope AES-256-GCM. O teste restaura em container independente
com dados em tmpfs e compara as linhas ordenadas. Não altera nem apaga a base original.
Arquivos `.aesgcm` ficam na pasta privada `backups`; a chave está em `keys/backup.key`.
Este mecanismo não é backup de produção e não cobre o futuro Lake/eventos de usuário.

## Estrutura e comandos

| Caminho | Responsabilidade |
|---|---|
| `apps/api` | Pacote FastAPI, `/health`, logs por allowlist |
| `apps/web` | React/TypeScript, status acessível, build estático com esbuild |
| `packages/lake` | Contrato `ObjectStore` e `LocalObjectStore` abstrato |
| `packages/*/README.md` | Fronteiras reservadas das próximas fases |
| `infra` | Compose, configuração ClickHouse e migrações SQL |
| `scripts` | Operação PowerShell e verificações sintéticas |
| `tests` | Segurança, infraestrutura, criptografia e contratos |
| `.github/workflows/ci.yml` | Checks e stack sintética em runner descartável |

```powershell
uv sync --frozen
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pytest -q
Push-Location apps/web
npm.cmd ci --ignore-scripts
npm.cmd run lint
npm.cmd test
npm.cmd run build
npm.cmd audit --audit-level=high
Pop-Location
```

As dependências efetivas estão em `uv.lock` e `apps/web/package-lock.json`.
Não executar scripts de instalação de dependências npm. O frontend só acessa `/health`
na própria origem, sem CDN, fontes ou telemetria externas. A publicação é via Nginx no Compose.
`python -m finance_api` é um entrypoint **de container**; fora dele use Uvicorn com
`--host 127.0.0.1`, nunca o entrypoint que escuta na interface interna Docker.

## Aceite

Leia [resultados e pendências](docs/phase-0-results.md), [arquitetura](docs/architecture.md),
[ameaças](docs/threat-model.md), [operação](docs/operations-runbook.md) e [ADRs](docs/adr/README.md).
O plano completo está em [docs/implementation-plan.md](docs/implementation-plan.md).

Não usar dados reais nesta Fase 0. Docker/ACL não criptografam discos; BitLocker, disco do
Docker/WSL e cópia de backup em meio separado precisam ser verificados antes de dados reais.
Implementation stops here for evaluation. Local Docker startup, security checks and synthetic
backup/restore have passed; remaining manual checks are listed in the validation report.
