# ADR-006: Eventos manuais independentes de rebuild

Data: 17/11/2026. Status: Direção aceita; execução na Fase 4.

## Contexto

Correções humanas não podem desaparecer na reconstrução de marts.

## Decisão

Regras, revisões e classificações serão eventos versionados com backup próprio e read-after-write.

## Alternativas

Atualização célula a célula ou edição somente em Gold perde rastreabilidade.

## Consequências

Definir contratos de revogação/precedência antes de endpoints de escrita; nenhum existe agora.
