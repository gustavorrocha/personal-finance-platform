# ADR-005: Append-only e última versão determinística

Data: 17/11/2026. Status: Direção aceita; execução a partir da Fase 3.

## Contexto

ReplacingMergeTree deduplica eventualmente; SELECT comum pode duplicar valores.

## Decisão

Definir versões monotônicas por chave, event_id para desempate e leitura FINAL/argMax documentada antes de marts.

## Alternativas

OPTIMIZE FINAL diário não é garantia de corretude.

## Consequências

Nenhum modelo de versões financeiro é implementado na Fase 0; testes de coexistência são futuros.
