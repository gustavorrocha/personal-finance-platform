# ADR-002: ClickHouse como único SGBD

Data: 17/11/2026. Status: Aceita na Fase 0.

## Contexto

Restrição vinculante do plano; operações interativas futuras precisam conviver com OLAP.

## Decisão

core, analytics e metadata são databases ClickHouse. Não adicionar SQLite, PostgreSQL ou Redis.

## Alternativas

Banco transacional adicional violaria o escopo e aumentaria operação.

## Consequências

Na Fase 0 há somente ledger de migração e tabela sintética; merges não oferecem unicidade transacional.
