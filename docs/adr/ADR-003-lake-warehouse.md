# ADR-003: Bronze externo e warehouse reconstruível

Data: 17/11/2026. Status: Aceita como direção; execução na Fase 1.

## Contexto

É necessário preservar a evidência original sem depender da sobrevivência do warehouse.

## Decisão

Bronze futuro em arquivos; Silver em core, Gold em analytics. Eventos manuais são estado independente.

## Alternativas

Raw canônico no ClickHouse não atende replay externo previsto no plano.

## Consequências

Não criar Bronze nesta entrega; backup futuro precisa cobrir Lake e eventos não reconstruíveis.
