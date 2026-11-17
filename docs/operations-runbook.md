# Operação e recuperação — somente sintético

1. `bootstrap.ps1` instala dependências congeladas, valida o diretório, restringe ACL e gera segredos.
2. `run_local.ps1` sobe o banco e Ollama, aplica SQL e aguarda saúde de API/web.
3. `load_synthetic.ps1` insere dois eventos determinísticos; repetir não adiciona linhas.
4. `verify_security.ps1` verifica publicações reais, redes, portas no host, saúde e logs com token falso.
   Faz também conexão de teste para IP externo no namespace de rede do Ollama; deve falhar.
5. `restore_test.ps1` cria novo backup criptografado, autentica o envelope, valida checksum,
   restaura em ClickHouse descartável em tmpfs e compara checksum/contagem das linhas.
6. `docker compose --env-file .env -f infra/compose.yaml down` para serviços preservando dados.

Network clarification: only the publishing frontend uses a non-internal bridge, with outbound
masquerading disabled and host bindings restricted to 127.0.0.1. Internal data and AI networks
remain isolated. The verifier tests external TCP blocking in the database and Ollama namespaces;
API/web outbound access remains possible on the tested Docker Desktop host. Configure host
firewall policy if stronger frontend egress restrictions are required.

O scanner de portas inclui loopback e IPv4 do hostname. Não substitui teste de outra máquina,
firewall, IPv6 ou inspeção do Docker Desktop/WSL. Um serviço local alheio nas portas sensíveis
provoca falha conservadora; investigue o processo em vez de enfraquecer a verificação.

Segredo perdido: parar a stack, remover somente os arquivos individuais `secrets/api_password`
e `secrets/health.xml` da pasta privada que foi conferida e executar bootstrap novamente;
recriar containers. Não publicar logs, hashes de senha ou arquivos de segredo.
Chave de backup perdida: backups existentes não poderão ser restaurados; não sobrescrever
`keys/backup.key`. Rotação e cópia em meio independente são pré-requisitos de uso real futuro.

Falhas de comandos retornam mensagem genérica; investigar localmente sem enviar dumps para CI.
Logs API preservam apenas evento e nível. Nginx não registra URL/headers e ClickHouse não
persiste query/text/trace logs. Isso reduz diagnóstico e será revisado quando houver ingestão.

A migração `0001` deve permanecer imutável. Hash divergente falha fechado.
DDL ClickHouse não é transação entre tabelas: uma interrupção exige repetir DDL idempotente.
Não executar dois migradores ao mesmo tempo. A tabela sintética não é um modelo financeiro.

Retenção nesta fase: apagar os arquivos sintéticos de backup de mais de sete dias sob supervisão,
após conferir caminho/ACL e verificar ao menos uma restauração. Não há remoção automática.
Meta de laboratório RPO: última execução do backup; RTO: até 15 min após Docker disponível,
**não medido**. Backups locais no mesmo disco não cobrem perda do notebook.

Antes de qualquer dado real: verificar BitLocker inclusive disco Docker/WSL, ACL herdada,
exclusão de cloud sync, backup criptografado em segundo meio com chave independente,
teste privado de restauração, política de retenção/exclusão e proteção do host.
Não existe comando de backup completo de produção nesta fase.

## Phase 1 recovery

Run `scripts/validate_bronze.ps1` after startup to verify capture retries, quarantine,
and isolated reconstruction. Use one writer at a time for capture and warehouse publication.

To recover from a ClickHouse loss, keep the private Lake directory, start a fresh local
instance with the migrations applied, and run `finance rebuild-warehouse --from-bronze`.
If index registration fails after manifest publication, retry the same capture or replay
its UUID once ClickHouse is available. When verification reports corruption, preserve the
capture and its quarantine marker for investigation. A quarantined run cannot be replayed.
The foundation backup covers the original synthetic probe. Back up the Lake independently.
