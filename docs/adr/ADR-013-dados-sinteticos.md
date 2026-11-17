# ADR-013: Separação entre sintéticos públicos e reais privados

Data: 17/11/2026. Status: Aceita na Fase 0.

## Contexto

CI/repositório não devem conter informações pessoais ou bancárias.

## Decisão

Fixtures inteiramente inventadas; runtime desta fase restrito a sintéticos; diretório privado fora de Git/cloud sync.

## Alternativas

Anonimizar extratos reais para CI ainda cria risco de reidentificação e vazamento.

## Consequências

Não enviar dumps/logs/volumes para CI. Liberar dados reais depende de fases e avaliação explícitas.
