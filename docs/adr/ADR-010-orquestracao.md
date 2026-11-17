# ADR-010: Sem Airflow ou metastore adicional

Data: 17/11/2026. Status: Aceita na Fase 0.

## Contexto

Orquestração pesada adiciona dependências e banco auxiliar proibido.

## Decisão

PowerShell e CLI local na V1; agendamento leve somente quando a fase operacional precisar.

## Alternativas

Airflow, filas e bancos auxiliares aumentam superfície sem benefício desta fase.

## Consequências

Falhas interrompem comandos; não há scheduler ou automação financeira.
