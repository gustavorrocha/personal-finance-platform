# ADR-011: Rede fechada e armazenamento protegido

Data: 17/11/2026. Status: Aceita na Fase 0.

## Contexto

O repositório pode estar em OneDrive; volumes, logs e segredos não devem acompanhar o código.

## Decisão

Bind somente loopback; banco/IA sem portas; secrets por arquivo externo com ACL; backup sintético AES-GCM.

Runtime clarification (17 November 2026): the publishing frontend uses a bridge with outbound
masquerading disabled and explicit loopback bindings. Internal-only frontend endpoints did
not produce active host port mappings. Data, AI and recovery remain internal. Docker Desktop
still permits frontend outbound TCP traffic; no-masquerade is not a firewall. The verifier
checks database/AI egress blocking and actual active host bindings. Stronger frontend egress
restrictions require host firewall policy, rather than claiming all networks are air-gapped.

## Alternativas

Docker volumes e localhost sozinhos não são criptografia ou autenticação.

## Consequências

Host é fronteira privilegiada; confirmar BitLocker/WSL, firewall e cópia independente antes de dados reais.
