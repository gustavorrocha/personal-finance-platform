# Modelo de ameaças — Fase 0

Ativos: arquivos de segredo locais, futura informação financeira, integridade de migrações,
chave/arquivo de backup e host Windows/WSL. Hoje somente fixtures sintéticas são permitidas.
Fronteiras: navegador→HTTP localhost; web→API; API→ClickHouse; operador→Docker;
container→volume; instalação→registries; futuro texto de provedor→LLM.
O usuário local e o daemon Docker são privilegiados; localhost não autentica outros processos.

Measured network boundary: the frontend publishing bridge is not internal; it has explicit
loopback bindings and outbound IP masquerading disabled. On the tested Docker Desktop host,
API/web external TCP connections still succeeded. Database/AI external TCP connections were
blocked on their internal networks. Outbound NAT settings are not a firewall, and local DNS
forwarding/host access are residual channels. Stronger frontend egress policy belongs in the
host firewall. The runtime verifier also requires active localhost mappings, not merely
requested port bindings in Docker configuration.

| Ameaça (STRIDE) | Controle | Verificação | Resposta |
|---|---|---|---|
| Roubo de segredo Pluggy (S/I) | Não existe integração/segredo nesta fase; futuros secrets por arquivo | Dependências e serviços não contêm cliente Pluggy | Revogar no provedor na fase futura; investigar host |
| Perda do notebook (I) | Somente sintéticos agora; BitLocker e backup em outro meio exigidos antes de reais | Conferência manual BitLocker/WSL pendente | Revogar segredos, recuperar de meio separado |
| Host comprometido (E/I/T) | Non-root, cap_drop, no-new-privileges, ACL, sem socket Docker montado | Testes estruturais; revisão de permissões do host | Parar stack, isolar/reinstalar host, rotacionar chaves |
| Logs/payload publicados (I/R) | Allowlist de logs, sem access/query logs, erros genéricos, ignore de secrets | Testes de exceção/token falso; scan de logs em runtime | Remover publicação e revogar qualquer segredo divulgado |
| Dependência maliciosa (T/E) | Locks, npm ignore-scripts, dependências mínimas, nenhum dado real em CI | npm audit; builds congelados; revisão de locks | Bloquear versão, reconstruir ambiente, rotacionar se necessário |
| Prompt injection em descrição (T/E) | Nenhuma inferência na fase; futuro LLM sem ferramentas financeiras | Sem consumidor de Ollama; teste de prompt fica para Fase 6 | Quarentenar sugestão, revisar classificador |
| Backup vazado/adulterado (I/T) | AES-256-GCM, chave separada do arquivo, hashes internos | Roundtrip, chave errada, adulteração e restauração isolada | Rejeitar envelope; trocar chave após comprometimento |
| Frontend exposto/DNS rebinding (S/I) | Bind 127.0.0.1, TrustedHost, CORS sem permissões, CSP, nenhuma escrita | Testes Host/Origin e inspeção real de PortBindings | Parar publicação, corrigir Compose/firewall |
| Docker Desktop/WSL excessivo (E) | Sem privileged/host network/socket; volumes mínimos | Testes estruturais e revisão manual de grupos/WSL | Remover privilégios, reconstruir containers |
| RCE no backend (E/I/D) | Imagem read-only, usuário restrito ao ledger, redes sem egress, limites | Config e usuário; teste HTTP de falha sanitizada | Parar API, rotacionar health secret, reconstruir imagem |
| Acesso cruzado entre redes (E/I) | AI só ai, banco só data, web só frontend, restore só recovery | Testes de membership e internal; probe egress no namespace Ollama | Desconectar rede indevida, revisar serviço dual-homed |
| DoS local (D) | Timeouts HTTP/SQL, memória/PIDs, sem mutações públicas | Limites estáticos; health degrada a 503 | Parar processo causador e restaurar disponibilidade |

Riscos residuais: containers com rede interna ainda dependem do firewall/daemon; host pode
acessar redes privadas e segredos montados. API é dual-homed. Diretório com nome não revela
todos os softwares de sincronização: conferir configurações reais. Docker não criptografa volumes.
O bootstrap protege ACL do diretório; execução não foi validada neste ambiente restrito.
Sem autenticação de produto nesta fase: não habilitar dados reais ou acesso remoto por esta API.
Não há garantia contra administrador/root malicioso ou captura de memória no host.

Backups sintéticos locais com chave no mesmo host exercitam criptografia e integridade,
mas não são uma estratégia de recuperação de desastre. CI não deve receber dados reais,
segredos privados ou upload de volumes/logs como artefatos. Modelos e egress de download
precisarão de bootstrap controlado separado na Fase 6; nenhum modelo é baixado agora.
