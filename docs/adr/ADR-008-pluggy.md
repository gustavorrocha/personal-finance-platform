# ADR-008: Integração somente leitura e auditoria prévia

Data: 17/11/2026. Status: Direção aceita; execução na Fase 2.

## Contexto

Cobertura real e paginação precisam de auditoria antes de ingestão.

## Decisão

Futura conexão read-only, cursor opaco em transações e paginação por endpoint; sem credenciais bancárias.

## Alternativas

Assumir cobertura completa ou implementar pagamentos conflita com o plano.

## Consequências

Nenhuma chamada, credencial, SDK, endpoint Pluggy ou auditoria real nesta entrega.
