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

## Historical verification snapshots

Data da verificação: 17/11/2026. **Implementação entregue para avaliação; aceite operacional
Docker ainda pendente. Não avançar para a Fase 1.**

O plano integral foi lido em `docs/plano_financas_datalake_clickhouse.md`, único arquivo
original deste workspace. `docs/implementation-plan.md` agora referencia esse plano.
O repositório Git foi inicializado localmente; nenhum remoto ou publicação foi criado.
O commit foi tentado e recusado por permissão em `.git/index.lock`; os arquivos permanecem
no workspace sem commit. Não houve solicitação de elevação nem alteração das permissões.

## Verificações executadas

| Check | Resultado observado |
|---|---|
| `uv lock` e `uv sync --frozen` | Passaram; workspace API/Lake instalado |
| `uv run --frozen pytest -q` | 17 testes passaram, nenhum ignorado |
| `uv run --frozen ruff check .` | Passou |
| `uv run --frozen ruff format --check .` | Passou |
| `npm ci --ignore-scripts` | Passou com lockfile |
| `npm run lint` | TypeScript estrito + Prettier passaram |
| `npm test` | 3 testes passaram, nenhum ignorado |
| `npm run build` | Build React estático passou |
| `npm audit --audit-level=high` | Zero vulnerabilidades na árvore final |
| `pip-audit --disable-pip --no-deps -r <export uv>` | Nenhuma vulnerabilidade conhecida |
| `docker compose -f infra/compose.yaml config --quiet` | Passou com caminho sintético por variável de ambiente |
| Parser PowerShell em todos os `.ps1` | Nenhum erro sintático |
| Contratos e controles estáticos | Redes internas, loopback, non-root, limites, ACL prevista, secrets em arquivos, logs restritos |
| Criptografia em processo | Roundtrip, adulteração e chave incorreta testados |

Versões executadas: Python 3.12.8, uv 0.11.6, Node 24.19.0, npm 11.17.0,
Ruff 0.17.5, Pytest 9.2.0, FastAPI 0.163.2, httpx 0.28.1,
cryptography 50.0.2, esbuild 0.28.2. Versões transitivas exatas nos lockfiles.

O Pytest emitiu um aviso de depreciação de Starlette TestClient com httpx.
Os testes continuam passando; avaliar migração do transporte de teste em atualização futura,
sem ocultar o aviso. pip-audit alerta sobre export sem hashes/`--no-deps`; a resolução foi
congelada via uv.lock e o arquivo auditado enumera as dependências transitivas.
`pluggy` no uv.lock é infraestrutura do Pytest, não SDK ou integração bancária.
Execuções npm agrupadas no sandbox encontraram `spawn EPERM`; os comandos individuais
`npm.cmd test` e `npm run build` foram executados depois e passaram na árvore final.

A auditoria inicial detectou ReDoS transitivo em picomatch. A versão consultada não tinha
correção publicada; remover o Vite eliminou a dependência, substituindo-o por build esbuild.
A versão final também corrige os avisos encontrados em esbuild e cryptography.
Não foi aplicado `npm audit fix --force`.

## Critérios de aceite que exigem Docker

`docker version` retornou **permission denied** no pipe `dockerDesktopLinuxEngine`.
Nenhum container foi iniciado neste ambiente. Validação de Compose não demonstra isolamento
real nem executa SQL, e testes com dependência substituída não provam saúde do ClickHouse.

| Critério do plano | Implementado | Evidência ainda necessária |
|---|---|---|
| `run_local.ps1` sobe stack e `/health` passa | Sim | Executar em Docker Desktop acessível |
| Segredo falso ausente dos logs | Testes unitários passaram + probe runtime pronta | Executar `verify_security.ps1` na stack |
| ClickHouse/Ollama inacessíveis externamente | Compose sem ports e redes internas testado | Port scan/inspect runtime e conferência LAN/IPv6/firewall |
| Backup/restore sintético | AES-GCM testado; export/restore Native implementado | Executar `load_synthetic.ps1` e `restore_test.ps1` |
| Nenhuma base extra | Configuração e dependências revisadas | Inspecionar stack em execução |
| Volumes protegidos | Bootstrap com ACL e validação de caminhos | Executar bootstrap, conferir ACL e BitLocker/WSL |
| CI sintética | Workflow pronto | Executar no GitHub após revisão/publicação autorizada |

Também pendentes: download/build das imagens pinadas, validação de permissões Linux dos
volumes/secret mounts, teste visual em navegador e revisão de digests/vulnerabilidades de imagens.
Nenhuma imagem foi tratada como validada só por possuir tag. PowerShell foi analisado,
mas bootstrap/operação completa não foram executados fora do workspace restrito.

## Sequência para avaliação

```powershell
.\scripts\bootstrap.ps1
.\scripts\check.ps1
.\scripts\run_local.ps1
.\scripts\load_synthetic.ps1
.\scripts\load_synthetic.ps1
.\scripts\verify_security.ps1
.\scripts\restore_test.ps1
```

O verificador exige exatamente 2 eventos, total Decimal 10.00, saúde em ambas as origens,
ausência de publicação sensível, redes internas e egress bloqueado no namespace Ollama.
O restore usa outra instância ClickHouse em tmpfs e não modifica a base de origem.
Não há backup completo de produção, Lake, replay Bronze, provedor, modelo ou cálculos
financeiros implementados. São escopos posteriores, e não pendências para ampliar esta fase.

Risco de uso: laboratório sintético, sem autenticação de produto e sem comprovação operacional
Docker nesta sessão. Nenhum dado real deve ser introduzido antes de avaliação e fases adequadas.

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
