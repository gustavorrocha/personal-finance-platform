# ADR-004: LocalObjectStore e contrato futuro

Data: 17/11/2026. Status: Aceita na Fase 0; implementação na Fase 1.

## Contexto

O pipeline futuro deve tolerar mudança do backend sem reescrever ingestão.

## Decisão

ObjectStore define escrita imutável, leitura, listagem de manifestos, checksum, verificação e retenção; LocalObjectStore permanece abstrato.

## Alternativas

MinIO/S3 agora adicionaria um serviço sem necessidade da Fase 0.

## Consequências

Fase 1 deverá validar traversal/symlinks, fsync, rename e manifesto por último com testes de queda.
