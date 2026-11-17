# ADR-001: Monorepo Python/TypeScript

Data: 17/11/2026. Status: Aceita na Fase 0.

## Contexto

API e domínio futuro precisam de fronteiras explícitas e checks reproduzíveis.

## Decisão

Workspace uv para API/Lake; npm separado para React. Ruff/Pytest e CI usam apenas dados sintéticos.

## Alternativas

Múltiplos repositórios duplicariam operação; workspace não exige serviços por pacote.

## Consequências

Manter uv.lock e package-lock.json; novos módulos só ganham implementação na fase prevista.
