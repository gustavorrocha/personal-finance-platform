# ADR-009: IA exclusivamente local

Data: 17/11/2026. Status: Preparação na Fase 0; inferência na Fase 6.

## Contexto

Dados financeiros reais não podem ir para LLM externa.

## Decisão

Ollama sem publicação, OLLAMA_NO_CLOUD=1 e rede interna ai; nenhum modelo ou consumidor agora.

## Alternativas

APIs LLM remotas não atendem à privacidade; baixar modelo em runtime exigiria egress.

## Consequências

Bootstrap de modelos será separado; saída será não confiável, validada e submetida à revisão.
