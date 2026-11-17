# ADR-012: Precisão e informação ausente

Data: 17/11/2026. Status: Direção aceita; execução financeira nas fases futuras.

## Contexto

Um número financeiro incorreto é falha crítica.

## Decisão

Decimal para dinheiro, datas econômicas distintas de timestamps UTC e qualidade explícita; ETF não define classe econômica.

## Alternativas

Float monetário, retorno inventado ou soma de versões produzem falsos resultados.

## Consequências

A Fase 0 testa Decimal só na fixture; não calcula retorno, exposição ou reconciliação.
