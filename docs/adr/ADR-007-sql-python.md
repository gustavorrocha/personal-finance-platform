# ADR-007: SQL analítico e Python financeiro

Data: 17/11/2026. Status: Direção aceita; execução nas Fases 4 e 8.

## Contexto

Modelagem dimensional e cálculo financeiro têm exigências distintas.

## Decisão

dbt-clickhouse para SQL; Python determinístico/Decimal para métricas complexas.

## Alternativas

Concentrar fórmulas financeiras em SQL dificultaria testes e tratamento de incompletude.

## Consequências

Não instalar dbt, cliente warehouse ou bibliotecas financeiras sem uso nesta fase.
