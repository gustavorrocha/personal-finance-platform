# Plano de implementação — Plataforma pessoal de finanças, Data Lake + ClickHouse Warehouse

**Versão:** 2.0 · **Data:** 17/11/2026\
**Status:** plano técnico e roteiro para agente de código (sem execução de código de produção)\
**Fontes iniciais:** bancos conectados à Pluggy/Open Finance.\
**Restrições:** ClickHouse é o **único SGBD**; tudo local-first; LLM exclusivamente local para dados reais; sem endpoints públicos na V1; Data Lake Bronze persistente, Silver/Gold no ClickHouse.

---

## 0. Resumo executivo e decisões

Construir um produto privado que unifique contas, cartões, gastos, patrimônio e investimentos, com histórico auditável e classificação econômica de ativos (inclusive ETFs de renda fixa e cofrinhos). Usar arquitetura de dados end-to-end:

```text
Bancos com consentimentos existentes na Pluggy
            │ HTTPS, serviço de ingestão isolado
            ▼
     Ingestion CLI / Python ───► manifestos, checksums, checkpoints (ClickHouse metadata)
            │
            ▼
DATA LAKE BRONZE (filesystem local seguro na V1; interface para S3-compatible)
   JSON original comprimido, imutável, versionado por coleta + manifesto
            │ replay e normalização
            ▼
CLICKHOUSE SILVER (core)
   contas, transações versionadas, faturas, posições, movimentos, instrumentos,
   eventos de classificação, reconciliação e histórico de saldos
            │ dbt-clickhouse + motor Python de performance
            ▼
CLICKHOUSE GOLD (analytics)
   fatos e dimensões, patrimônio diário, despesas, caixa, exposição e retornos
            │ consultas via FastAPI
            ▼
React / TypeScript: Dashboard privado local
            ▲
Ollama + Qwen3 pequeno: sugestões locais de classificação (não decide fluxos financeiros)
```

### Decisões vinculantes

1. **ClickHouse é o único banco** do produto. Um Data Lake de arquivos e um armazenamento de modelos não são bancos adicionais; não adicionar PostgreSQL/SQLite ao runtime.
2. **Bronze é uma camada persistente externa ao ClickHouse**: arquivos originais + metadados de proveniência + integridade; pode ser consultada/transformada para Silver. `raw` deixa de ser a fonte canônica dentro do ClickHouse.
3. **Silver = banco `core`; Gold = banco `analytics`** no ClickHouse; `metadata` armazena checkpoints, regras, eventos e testes. Em ClickHouse os nomes são *databases* separados, não schemas PostgreSQL.
4. **Data Lake inicialmente em filesystem local criptografado**, com interface `ObjectStore` e layout compatível com armazenamento de objetos; adicionar serviço S3-compatible local depois de estabilizar o MVP. Se o aprendizado de S3 for prioritário, substituir o backend sem alterar o pipeline. Não adicionar MinIO nem outro serviço sem validar suporte, manutenção e hardening.
5. **Somente inferência local** para dados reais via Ollama; nenhuma API LLM externa. Testes de comparação com APIs gratuitas, caso desejados, exclusivamente com dados sintéticos.
6. **Sem Airflow na V1**, para respeitar o requisito de único SGBD e reduzir a superfície de ataque. CLI + agendador leve; evolução de orquestração documentada como ADR futura.
7. **Sem pagamentos, ordens ou automações financeiras**. A integração é somente leitura.
8. **Dado financeiro incorreto é falha crítica**: nunca somar versões duplicadas nem inventar retornos; toda estimativa deve ser identificada como tal.

## 1. Objetivos de produto

### Dashboard — gastos
- Gastos por categoria, subcategoria, estabelecimento, cartão/conta e instituição; receitas e fluxo de caixa, comparativos e recorrência.
- Transferências próprias, pagamento de fatura e aplicação/resgate **não são despesas finais**. Gastos do cartão devem ser apropriados conforme data da compra, com parcelas e estornos modelados separadamente.
- Interface de revisão manual, regras por estabelecimento, detecção de transações sem classificação e comparativo categoria Pluggy × regra × LLM.

### Dashboard — patrimônio
- Saldos bancários, cartões/obrigações, posições de investimento, exposição por classe econômica e instituição, histórico e liquidez.
- Tratamento explícito de produtos que apareçam como conta **ou** investimento; evitar dupla contagem.
- ETF é **tipo de veículo**, não classe econômica. Suporte para exposição ponderada de instrumentos híbridos.

### Dashboard — performance
- Posição, custo quando disponível, ganhos realizados/não realizados, juros/dividendos/cuponagens, taxas/tributos, TWR e XIRR quando computáveis.
- Benchmark CDI e outros índices por fontes documentadas; distinguir retorno observado, reconstruído, estimado e indisponível.
- Cofrinhos/caixinhas: verificar cobertura efetiva e usar movimentos + snapshots; uma taxa contratada não representa retorno efetivo.

### Operação e governança
- Freshness por fonte, cobertura da conexão, qualidade, linage Bronze → Silver → Gold, execuções, falhas, reprocessamento, backups e testes de restauração.

**Não objetivos:** multiusuário, controle de portfólio da gestora, movimentar dinheiro, aconselhamento financeiro, acesso remoto público, LLM remota com dados reais, streaming de baixa latência e lakehouse com Iceberg no MVP.

## 2. Arquitetura e fronteiras de segurança

| Componente | Responsabilidade | Exposição de rede |
|---|---|---|
| `ingestion` Python | Autenticar na Pluggy, ler dados, gravar Bronze e registrar manifests | Saída HTTPS para Pluggy; sem porta pública |
| `bronze_store` | JSON/JSONL gzip imutável; Parquet opcional derivado | Volume local restrito; nenhum servidor na V1 |
| `clickhouse` | Único SGBD: Silver, Gold, metadata | Apenas rede privada Docker; nunca público |
| `dbt` efêmero | Construir e testar modelos do warehouse | Somente ClickHouse |
| `performance` Python | Cálculos financeiros e escrituração de métricas validadas | Sem internet por padrão |
| `ollama` | Classificar descrições sanitizadas | Rede isolada; cloud desativada |
| `api` FastAPI | Consultar Gold, editar regras, classificar, mostrar saúde | Bind em `127.0.0.1` no host |
| `web` React | Apresentar dashboards e revisões | `127.0.0.1` |
| `scheduler` | Executar CLI incremental e manutenção | Sem exposição pública |

### Política de rede
- Criar redes Docker separadas (`frontend`, `data`, `ai`, `egress`) e anexar somente os serviços necessários. Redes Docker *não substituem firewall*: a máquina host, containers dual-homed e política de egress devem ser considerados no modelo de ameaças.
- Em V1, **não publicar** 8123/9000 do ClickHouse, 11434 do Ollama ou portas do Lake; se uma ferramenta local precisar, usar túnel temporário ou binding em localhost com configuração explícita.
- Segredos jamais no repositório, imagens ou logs. Preferir arquivo de secrets montado com ACL e rotação. Conceder apenas credenciais da Pluggy necessárias; não coletar senhas bancárias.
- Configurar `OLLAMA_NO_CLOUD=1`, carregar modelos por etapa separada e bloquear egress do serviço de inferência em operação. Um container sem egress também não baixa modelos: prever bootstrap controlado.
- Criptografar volumes via BitLocker/LUKS/FileVault e backups com ferramenta e chave independentes; Docker por si só **não criptografa volumes**.
- Evitar telemetria, error tracking, analytics externos e saída de dados financeiros para GitHub Actions; CI só com dados sintéticos.

### Modelo de ameaças obrigatório
Documentar riscos de: roubo de segredo Pluggy; perda do notebook; comprometimento do host; logs/payloads acidentalmente publicados; dependências maliciosas; prompt injection em descrição de transação; backup vazado; frontend local inadvertidamente exposto; Docker Desktop / WSL2 com permissões excessivas; RCE em backend; acesso cruzado de redes. Para cada risco, associar controle, teste e procedimento de resposta.

## 3. Data Lake Bronze

### Conceito e contrato
O Lake é uma **landing zone durável** para respostas da Pluggy: objetos imutáveis, versionamento por observação, informações de extração e checksums. JSON original é a fonte da verdade de ingestão. Arquivos Parquet são opcionais como *derivados* compactados para análise e aprendizado (não substituir a evidência original).

Layout proposto (dados reais fora da árvore Git):

```text
private_data/lake/
  bronze/source=pluggy/resource=accounts/ingestion_date=YYYY-MM-DD/run_id=<uuid>/part-0001.jsonl.gz
  bronze/source=pluggy/resource=transactions/ingestion_date=YYYY-MM-DD/run_id=<uuid>/part-0001.jsonl.gz
  bronze/source=pluggy/resource=investments/ingestion_date=YYYY-MM-DD/run_id=<uuid>/part-0001.jsonl.gz
  bronze/source=pluggy/resource=investment_movements/ingestion_date=YYYY-MM-DD/run_id=<uuid>/part-0001.jsonl.gz
  bronze/source=pluggy/resource=bills/ingestion_date=YYYY-MM-DD/run_id=<uuid>/part-0001.jsonl.gz
  manifests/ingestion_date=YYYY-MM-DD/run_id=<uuid>/manifest.json
  quarantine/run_id=<uuid>/...
  derived/parquet/...   # opcional; regenerável
```

**Não colocar identificadores pessoais** no caminho (CPF, número de conta, nome completo); `institution` é rótulo seguro e pode ser um campo no manifesto. A listagem de arquivos já revela metadados: ACLs também se aplicam a manifestos.

Cada objeto/manifesto registra: `run_id`, `object_id`, `resource`, `item_alias` não sensível, `retrieved_at_utc`, `source_endpoint` sem query secrets, versão do coletor, intervalo de referência, quantidade de registros, `sha256`, tamanho, nome do arquivo, `schema_fingerprint`, `consent_state`, status `complete|quarantined`, e referencial dos objetos anteriores quando houver. O manifesto é gravado por último e indica que o batch está **completo e recuperável**.

### Estratégia transacional para arquivos e ClickHouse
1. Baixar e validar resposta/páginas em memória ou staging protegido.
2. Gravar arquivo `*.tmp`, `fsync`, verificar SHA-256, renomear atomicamente para arquivo definitivo no mesmo filesystem.
3. Gravar manifesto de lote validado, **somente após** todos os objetos estarem duráveis.
4. Registrar o manifesto no ClickHouse `metadata.bronze_objects` com `run_id`, hash, caminho e `status`.
5. Processar Silver com identificador determinístico de objeto/registro. Falha entre etapas será resolvida por replay de manifesto (at-least-once + idempotência lógica).
6. Checkpoint de paginação só avança depois de o dado Bronze estar persistido e a etapa exigida ter sido concluída.
7. Implementar `finance lake verify`, `finance lake list`, `finance replay --run-id ...` e `finance rebuild-warehouse --from-bronze`.

### Evolução S3-compatible
- Interface `ObjectStore`: `put_immutable`, `get`, `list_manifests`, `checksum`, `verify`, `delete_with_retention_policy`.
- Implementação inicial `LocalObjectStore`; adaptação futura `S3ObjectStore` com bucket privado, versionamento e criptografia.
- Ao incluir um storage local S3-compatible, validar manutenção, imagens pinadas, política de credenciais e segurança da rede. **Não criar um segundo banco para a aplicação**. Metadados internos de um serviço de object storage não devem virar um novo serviço de SQL consultável pelo app.
- Implementar integração ClickHouse com arquivos Parquet via funções de arquivo/objeto quando o backend estiver disponível; não acoplar toda transformação ao endpoint de storage.

## 4. Warehouse no ClickHouse: databases e tabelas

**Databases:** `core`, `analytics`, `metadata`. `raw` deixa de existir como base canônica; pode haver tabelas transitórias `landing`/`staging` com retenção curta, reconstruíveis do Lake.

### 4.1 Silver — `core`

| Tabela | Grão / campos-chave | Motor e estratégia |
|---|---|---|
| `core.institution_observations` | conector, instituição, observado_em | MergeTree, append |
| `core.connection_versions` | item/conexão, estado, versão, timestamps | ReplacingMergeTree(version) + visão correta |
| `core.account_versions` | account_key, tipo, moeda, saldo, effective_at, version | ReplacingMergeTree(version) |
| `core.bank_transaction_versions` | logical_tx_key, data econômica, valor Decimal, moeda, status, deleted, version | ReplacingMergeTree(version) |
| `core.credit_card_bill_versions` | bill_key, vencimento, fechamento, total, version | ReplacingMergeTree(version) |
| `core.instrument_versions` | instrument_key, identificadores ISIN/CNPJ/ticker, termos econômicos, version | ReplacingMergeTree(version) |
| `core.investment_position_observations` | account/instrument/value_date/observed_at, quantidade, valor | MergeTree, append |
| `core.investment_movement_versions` | movement_key, tipo, montante, data, version | ReplacingMergeTree(version) |
| `core.balance_observations` | account_key, data econômica e captura, saldo | MergeTree, append |
| `core.asset_exposure_events` | instrumento, classe econômica, peso, vigência, origem, versão | MergeTree, append |
| `core.classification_events` | transaction_key, categoria, origem, decisão, revision/version | MergeTree, append |
| `core.transaction_link_events` | relação lógica entre pagamentos/transferências/aplicações | MergeTree, append |
| `core.market_data_observations` | ativo/benchmark, data, valor/taxa, provedor | MergeTree, append |

**Grão é obrigatório:** cada tabela terá documentação de sua chave lógica, datas de vigência vs observação, regras de duplicação e política de tombstones. Nunca usar apenas ticker para identificar ativo. Suportar mesma emissão em contas diferentes e múltiplos CDBs com taxas diferentes.

**Tipos:** `Decimal` para dinheiro e taxas (escala compatível), `DateTime64(3, 'UTC')` para instante técnico; `Date` para competência e data econômica; `LowCardinality(String)` para enums adequados, evitando `Float` para valores monetários. Não usar dados de cliente, conta ou transações em chaves de logs textuais.

### 4.2 Gold — `analytics` (modelo dimensional)

**Dimensões:**
- `dim_date`: calendário, semana/mês/ano, dia útil quando disponível.
- `dim_institution`: instituição, conector, cobertura.
- `dim_account`: conta pseudonimizada, instituição, tipo, moeda (sem PII no frontend).
- `dim_instrument`: instrumento, tipo de veículo, indexador, liquidez, emissor, vencimento.
- `dim_asset_class`: classe/subclasse econômica com hierarquia e versão.
- `dim_category`: gastos/receitas com taxonomia e hierarquia.
- `dim_merchant`: estabelecimento canônico e aliases; não armazenar dados pessoais desnecessários.

**Fatos e grãos:**
- `fct_financial_transactions`: **uma linha por transação lógica atual** (com informação de origem e natureza); sem contar versões antigas.
- `fct_expenses`: **uma linha por evento reconhecido como despesa** (compra/estorno/parcela conforme convenção única), excluindo transferências próprias e pagamentos de fatura.
- `fct_cashflow`: **um evento econômico** com direção, conta e tipo, separado de despesa categorizada.
- `fct_investment_movements`: **uma movimentação de investimento** reconciliada.
- `fct_positions_daily`: **instrumento × conta × data de referência**; flag `observed|carried|estimated` e idade da observação.
- `fct_account_balances_daily`: **conta × data** com qualidade/freshness.
- `fct_asset_allocation_daily`: **data × classe econômica × conta**, distribuindo ETFs multiativos por pesos válidos.
- `fct_performance_daily`: **carteira/ativo × data**, com valor inicial/final, fluxos, resultado, retorno, método e qualidade.
- `fct_net_worth_daily`: **data × instituição/conta/componente**, com tratamento de dívida/conta cartão e duplicação.
- `fct_data_coverage_daily`: **recurso × instituição × data**, completude, idade e flags.

**Dimensões lentas:** estudar SCD Tipo 2 para classes de ativos, conta e cadastro de instrumentos (vigências). Começar com snapshots/versionamento e `valid_from`/`valid_to` derivados; só complexificar após necessidade real.

**Serviço de consultas:** API lê Gold e, em detalhes operacionais, Silver; nunca agrega diretamente JSONs brutos a cada renderização. Views e marts devem expor status de completude e data de referência.

### 4.3 `metadata` (controle e auditabilidade)
- `bronze_objects`, `ingestion_runs`, `run_events`, `sync_checkpoints_events`, `schema_migrations`.
- `model_build_runs`, `data_quality_results`, `source_freshness`, `quarantine_events`.
- `classification_rule_events`, `classification_review_events`, `app_settings_events`, `model_registry`.
- `reconciliation_events`, `rebuild_runs`, `backup_manifest_events`.

**Separar dados reconstituíveis e não reconstituíveis:** Bronze + eventos de classificação/regra/revisão são *stateful*. Gold, modelos Silver derivados e projeções são reconstruíveis. Fazer **backup também dos eventos de usuário do ClickHouse**, em meio separado, para permitir replay após perda da base.

### 4.4 Estratégia de atualizações no ClickHouse
- Todas as alterações interativas são **eventos versionados**; nenhuma dependência de `UPDATE`/`DELETE` por célula.
- `ReplacingMergeTree` faz deduplicação eventual em merges; **não considerar SELECT comum como estado correto**. Para leituras exatas, `FINAL` ou agrupamento determinístico com `argMax` e tie-break confiável. Definir versões monotônicas por chave lógica e desempate por event_id. Não usar `OPTIMIZE FINAL` como correção diária.
- Em marts, evitar agregar diretamente eventos `ReplacingMergeTree` sem colapsar versões: isso gera duplicações silenciosas. Recomendar dbt `view`/rebuild idempotente primeiro, incremental apenas com estratégia de reconciliação documentada e testada.
- API deve garantir leitura após escrita da correção manual (flush do lote + consulta consistente); inserir eventos em lotes pequenos controlados e medir parts.

## 5. Pipeline da Pluggy e auditoria de cobertura

### 5.1 Auditoria obrigatória antes da primeira carga completa
Implementar `finance audit-coverage`: conferir itens/conexões, conectores, status, recursos disponíveis, contas, cartões, investimentos, movimentos, faturas e datas. **Não assumir** cobertura de cofrinhos nem do histórico completo. Produzir relatório **sem saldos e sem descrições sensíveis**; contagens e percentuais de campos disponíveis bastam.

### 5.2 Endpoints e paginação
- Usar `GET /v2/transactions` com `next` opaco, preservando a query string retornada, até `null`. Não usar `GET /transactions` legado.
- `GET /investments`, movimentações de investimento, faturas e outros endpoints paginados por `page`, `pageSize`, `totalPages`; encapsular a estratégia por endpoint.
- Para a reconexão de um item Pluggy, os IDs podem mudar; não deduplicar entre itens unicamente por valor e data: usar provider identifiers e revisão de pares ambíguos.
- Planejar rechecagem de janela recente para `PENDING -> POSTED`, estornos e exclusões; webhook remoto exige perímetro de segurança e não será habilitado no MVP.
- Respeitar limites, backoff em 429/5xx, timeouts, circuit breaker simples, contagem de páginas e manifestos de falha.

### 5.3 Ordem de sincronização
1. Conexões/consentimentos e instituições.
2. Contas e saldos + cartões e faturas.
3. Transações por conta e janela de datas.
4. Produtos de investimento + posições e movimentações.
5. Persistir Bronze com manifestos.
6. Validar integridade e transformar Silver.
7. Executar regras de reconciliação e classificação.
8. Construir Gold e qualidade; confirmar checkpoint.

O replay deve funcionar **sem Pluggy disponível**, lendo somente Lake e eventos persistidos.

## 6. Regras de negócio financeiras

### 6.1 Despesas e conciliação
Definir `movement_nature`: `expense`, `income`, `internal_transfer`, `credit_card_settlement`, `investment_contribution`, `investment_redemption`, `tax`, `fee`, `reversal`, `unknown`. **Separar natureza financeira de categoria de consumo.**

Casos obrigatórios:
- Compra no cartão conta como despesa; pagamento da fatura apenas liquida passivo, sem segunda despesa.
- Transferência entre contas próprias não é receita/gasto; conciliar duas pontas com tolerância temporal e identificadores, evitando fusão irreversível em caso ambíguo.
- Aporte/resgate altera composição patrimonial e fluxo da carteira, não o consumo.
- Estorno, chargeback, compras parceladas, juros rotativos e tarifas têm tratamento próprio; documentar se a competência é compra ou parcela, com alternância de visualização apenas se consistentemente suportada.
- Evitar contar como patrimônio duas vezes dinheiro em conta e saldo de produto representado em duas APIs. Reconciliar por vínculo de origem.

### 6.2 Classificação econômica
Campos separados: `instrument_type` (`ETF`, `CDB`, `AÇÃO`, `FII` etc.) e `economic_exposure` (`renda_fixa_pos`, `renda_fixa_ipca`, `renda_fixa_pre`, `acoes_br`, `acoes_global`, `caixa`, `outros` etc.).

- ETF pode ser de renda fixa. Mapear por instrumento/ISIN/benchmark/mandato, não pelo sufixo da sigla.
- Permitir múltiplas exposições `instrument × economic_class × weight × valid_from/to`; pesos válidos devem somar 1 (com tolerância parametrizada).
- Suportar override manual auditado e origem `provider|reference|rule|manual`.
- Não depender de um cadastro externo de preços antes de testar cobertura histórica de instrumentos reais.

### 6.3 Motor de rentabilidade
**Métricas:** P&L realizado/não realizado, retorno por ativo, TWR por período, XIRR quando os fluxos forem datados e suficientes, comparação com CDI e outras referências.

- Calcular com `Decimal`, datas econômicas explícitas, ordem temporal determinística e identificação de moeda.
- TWR exige avaliações consistentes nos limites de subperíodos e tratamento de entradas/saídas externas. Sem snapshots adequados, não produzir TWR exato.
- XIRR resolve fluxos datados incluindo valor terminal; tratar múltiplas raízes, ausência de raiz e sinais insuficientes como indisponibilidade/alerta; não forçar um número.
- Rentabilidade líquida/bruta deve ter convenção explícita sobre taxas, tributos e dividendos; não misturar.
- Posição transferida, amortização, desdobramento e renda fixa com remuneração contratada exigem ajustes e testes específicos.
- Cofrinhos: reconstruir via saldo diário ajustado por fluxos onde possível; valor esperado com taxa contratada é **estimativa**, nunca observado.
- `quality_status`: `observed`, `reconstructed`, `estimated`, `partial`, `unavailable`; incluir `coverage_period`, `missing_days`, `pricing_source` e `methodology_version`.
- CDI e preços devem vir de fontes externas documentadas e auditadas (com política de disponibilidade/caching); não inventar benchmarks na ausência de fonte.

## 7. Classificação local por LLM

1. Executar conciliação e regras determinísticas antes de IA.
2. Reduzir descrição a texto útil, removendo CPF, conta, identificadores pessoais e demais PII desnecessárias.
3. Cache por descrição normalizada + contexto não sensível + versão do modelo/taxonomia.
4. Usar Ollama local com modelo inicial **Qwen3 1.7B quantizado**, sujeito a benchmark real de CPU/RAM; opções menores/maiores só após medição.
5. Gerar resposta estruturada fechada: `category_id`, `requires_review`, `explanation_short`; validar por Pydantic. Rejeitar categorias não cadastradas.
6. Registrar evento de sugestão e revisão humana; precedência de decisão `manual > rule > trusted_provider > llm`, com suporte para revogação.
7. Não executar instruções presentes na descrição da transação: entrada é **dado não confiável** (teste de prompt injection obrigatório).
8. Comparar com baseline regras/Pluggy em dataset rotulado local (real nunca sobe ao CI); métricas de macro-F1, precisão por categoria, taxa de revisão, latência, RAM e proporção de schema válido. Não interpretar autoconfiança textual do modelo como probabilidade calibrada.
9. Garantir, por teste de egress, que requests reais não saem para NVIDIA/OpenRouter/OpenAI ou qualquer serviço LLM remoto.

## 8. dbt, transformação e qualidade

- dbt-clickhouse com versões compatíveis **fixadas e testadas em CI**; não assumir que todas as features de snapshots/incrementais funcionam igual a PostgreSQL.
- Áreas `models/staging` (arquivo/landing → coerção), `models/core` (Silver), `models/marts` (Gold), `tests`, `seeds` (taxonomia sintética e tabelas estáticas).
- Separar **SQL de modelagem** de **Python financeiro**: reconstruir métricas complexas via motor determinístico com testes de exemplo e inserir resultados em Gold, posteriormente expor via dbt.
- Contratos e testes: `not_null`, unicidade **lógica** de chave atual, relacionamentos relevantes, somas de exposições, reconciliação de saldo/movimentos, não duplicidade de faturas, estado de versões, qualidade de snapshots e freshness.
- Testes de reconciliação com tolerância monetária explícita (sem arredondamento prematuro), e validação de que `rebuild` produz os mesmos indicadores para os mesmos manifestos/eventos.
- Métricas observáveis: atraso Pluggy→Bronze, Bronze→Silver, Silver→Gold; registros rejeitados, categorias pendentes, instrumentos sem classe, dias sem preço, taxa de classificações aceitas, estabilidade das consultas.

## 9. Estrutura de projeto

```text
personal-finance/
├── README.md
├── docs/
│   ├── architecture.md
│   ├── threat-model.md
│   ├── financial-methodology.md
│   ├── data-contracts.md
│   ├── operations-runbook.md
│   └── adr/ADR-001-...md
├── infra/
│   ├── compose.yaml
│   ├── clickhouse/config.d/
│   ├── clickhouse/users.d/
│   └── migrations/
├── apps/
│   ├── api/src/
│   └── web/src/
├── packages/
│   ├── pluggy_client/src/
│   ├── ingestion/src/
│   ├── lake/src/             # LocalObjectStore, S3ObjectStore (fase posterior)
│   ├── domain/src/
│   ├── reconciliation/src/
│   ├── classification/src/
│   └── performance/src/
├── analytics/
│   ├── dbt_project.yml
│   ├── models/staging/
│   ├── models/core/
│   ├── models/marts/
│   ├── tests/
│   └── seeds/
├── tests/
│   ├── fixtures/synthetic/
│   ├── integration/
│   ├── financial/
│   ├── e2e/
│   └── security/
├── scripts/
│   ├── bootstrap.ps1
│   ├── run_local.ps1
│   ├── backup.ps1
│   ├── restore_test.ps1
│   └── load_synthetic.ps1
├── .env.example
├── .gitignore
├── pyproject.toml
└── uv.lock

# private_data/ fica FORA do repositório e de diretórios sincronizados na nuvem
```

**Ferramentas:** Python 3.12+, `uv`, Ruff, Pytest, Pydantic, httpx, clickhouse-connect, dbt-core + dbt-clickhouse, FastAPI, React + TypeScript, TanStack Query, biblioteca de gráficos, Docker Compose, Ollama. Usar scripts Windows/PowerShell e CI GitHub Actions sem dados reais.

## 10. CLI e endpoints privados

### CLI (indicativa)

```bash
finance doctor
finance audit-coverage --redact
finance sync --resource all
finance sync --resource transactions --item-alias bank-1
finance lake verify
finance lake list --run-id <run_id>
finance replay --run-id <run_id>
finance build-silver
finance classify --pending
finance build-gold
finance validate
finance rebuild-warehouse --from-bronze
finance backup
finance restore --verify-only
```

### API local

```text
GET  /health
GET  /api/coverage
GET  /api/net-worth?from=&to=
GET  /api/expenses?from=&to=&category=&account=
GET  /api/transactions?status=&page=
POST /api/transactions/{id}/classifications  # evento append-only
GET  /api/assets
POST /api/assets/{id}/exposures       # evento append-only
GET  /api/positions?date=
GET  /api/performance?from=&to=&method=
GET  /api/pipelines/runs
POST /api/admin/sync                  # apenas localhost + proteção específica
```

API com esquema OpenAPI, validação, limites de consulta, CORS fechado, bind local e proteção contra CSRF quando houver cookies. Sem expor segredo Pluggy ao navegador. Se for necessário acesso remoto, definir arquitetura de autenticação e acesso privado em ADR separado antes de habilitar.

## 11. Etapas incrementais e critérios de aceite

### Fase 0 — Repo, segurança e infra local
**Implementar:** monorepo, ADRs, Docker Compose com ClickHouse, Ollama preparado (sem modelo real obrigatório), FastAPI mínimo, React mínimo, volumes protegidos, redes, migrações, scripts PowerShell, CI sintética.
**Aceite:** `run_local.ps1` sobe stack, `/health` passa; segredo falso nunca aparece em logs; scan de portas confirma ClickHouse/Ollama inacessíveis externamente; teste de backup/restore sintético; nenhuma base extra.

### Fase 1 — Data Lake Bronze e contrato de armazenamento
**Implementar:** `LocalObjectStore`, gravação atômica, manifestos, hashes, quarentena, verificação, índices `metadata.bronze_objects`, fixtures de API sintéticas, replay sem rede.
**Aceite:** duplicar a mesma carga não duplica Bronze logicamente, quedas após gravação de objetos ou manifesto são recuperadas; corrupção detectada por hash; rebuild a partir do Lake sintético funciona; nenhum dado real em paths do Git.

### Fase 2 — Auditoria das conexões Pluggy
**Implementar:** cliente read-only, conexão a itens existentes, resumo de cobertura, paginação por cursor e por página, relatório redigido.
**Aceite:** relatório por fonte mostra recursos, contagens e janela de disponibilidade, incluindo status dos cofrinhos; não armazena nem divulga credenciais, saldos ou transações em logs/artefatos.

### Fase 3 — Ingestão real e Silver
**Implementar:** coleta completa/incremental, Bronze imutável, versionamento `core`, tratamento de `PENDING`, reconexão e tombstones, metadados de execução.
**Aceite:** reexecutar a mesma coleta e reprocessar intervalo mantém contagens e totais; erro em página não avança checkpoint; leituras “atuais” não contêm duplicatas.

### Fase 4 — Conciliação, classificação determinística e Gold financeiro
**Implementar:** reconciliação de faturas e transferências, regras, eventos manuais, modelo dimensional `fct_expenses`, `fct_cashflow`, `dim_*`, testes dbt.
**Aceite:** cenários sintéticos complexos fecham sem contar consumo duas vezes; alteração manual é visível imediatamente e sobrevive a rebuild.

### Fase 5 — Dashboard útil (MVP de produto)
**Implementar:** FastAPI, React, visão de gastos, patrimônio, contas, histórico, páginas de revisão, freshness e erros.
**Aceite:** dados sintéticos E2E e dados reais localmente; filtros coerentes e zero acesso externo não autorizado; cards e tabelas reconciliam.

### Fase 6 — LLM local
**Implementar:** Ollama restrito, classificação em lotes, taxonomia, cache, validação estruturada, benchmark e revisão.
**Aceite:** modelo sem egress; saída válida ou revisão; nenhuma regra financeira substituída por LLM; benchmark reproduzível com dataset sintético.

### Fase 7 — Instrumentos e exposição econômica
**Implementar:** cadastro enriquecido, veículos vs classes, regra multi-classe, ETFs, CDBs, cofrinhos, alocação Gold e controles de cobertura.
**Aceite:** pesos somam 100% em cada vigência; posição/conta não duplicada; investimentos não classificados aparecem como pendência, nunca desaparecem do total.

### Fase 8 — Rentabilidade e benchmarks
**Implementar:** snapshots, movimentos, preço/taxa, motor de retorno, TWR/XIRR, testes golden cases, visualização de qualidade.
**Aceite:** cálculos conferem com casos manuais; incompletude retorna `partial|unavailable|estimated`; cofrinho sem histórico não recebe número “preciso”.

### Fase 9 — Operação, S3 e portfólio
**Implementar:** agendamento leve, backups incrementais e verificação de restauração, observabilidade, adaptação opcional S3-compatible local, Parquet derivado, benchmark ClickHouse e README com dataset sintético demonstrativo.
**Aceite:** perder ClickHouse não impede reconstruir Silver/Gold do Lake + restauração dos eventos não derivados; perda do Lake coberta por backup; nenhuma informação pessoal no repositório ou evidências públicas.

**Ordem de dependência:** 0 → 1 → 2 → 3 → 4 → 5; Fase 6 e 7 podem ser desenvolvidas em paralelo depois de 4; 8 depende de 3 + 7 e disponibilidade de histórico; 9 consolida operação e portfólio.

## 12. Testes e métricas obrigatórias

| Categoria | Cenário | Comportamento esperado |
|---|---|---|
| Lake | Queda após escrever JSON mas antes do manifesto | Lote não é considerado committed; recovery determinístico |
| Lake | Arquivo alterado | SHA-256 falha e objeto vai para quarentena |
| Ingestão | Cursor retorna múltiplas páginas e `next=null` | Todas as páginas sem perder/duplicar registros |
| Ingestão | Retry de sincronização | Mesmas chaves lógicas e mesmos totais |
| ClickHouse | `ReplacingMergeTree` com versões coexistentes | Gold resolve somente última versão válida |
| Finanças | Compra no cartão + pagamento de fatura | Uma despesa, um settlement |
| Finanças | Transferência própria entre duas contas | Zero receita/despesa líquida |
| Finanças | Aplicação/resgate | Mudança de patrimônio, não despesa |
| Finanças | ETF de renda fixa | Classe econômica de renda fixa, não ações |
| Finanças | Posição duplicada em conta/cofrinho | Uma exposição econômica |
| Retornos | Aportes em datas diferentes | XIRR/TWR coerentes com metodologia e cobertura |
| Retornos | Fluxos incompletos | `unavailable` ou `partial`, nunca número inventado |
| LLM | Prompt injection em descrição | Não executa instruções, só classifica conteúdo |
| Segurança | Container IA tenta acessar internet | Bloqueado e teste registra falha esperada |
| Segurança | Backup restaurado em ambiente limpo | Dados e eventos reconciliam com checksums |

**KPIs de pipeline:** freshness, % conexões saudáveis, total capturado por recurso, % campos nulos críticos, falhas/1000 registros, divergência de reconciliação, % ativos classificados, % transações pendentes, latência p50/p95 do dashboard, tempo de rebuild e verificações de backup.

## 13. Backup, retenção e recuperação

- Fazer backup criptografado do Lake **e** dos eventos ClickHouse que não são reproduzíveis (regras, classificações, revisões, metadados críticos); também manter backup completo da instância para recuperação rápida.
- Guardar `run_id`, checksum e cópia do manifesto em backup; teste periódico em workspace isolado, com dados sintéticos automatizados e teste manual privado para dados reais.
- Estabelecer retenção explícita para dados sensíveis; exclusões precisam propagar para versões em arquivos e backups conforme política definida. Imutabilidade operacional não é retenção eterna obrigatória.
- Documentar RPO/RTO pretendidos; em uso local, interrupção do computador e falta de sincronização devem aparecer no dashboard como *stale*.
- Reconstrução deve separar: (a) recuperar Lake; (b) recuperar eventos manuais e metadados essenciais; (c) refazer Silver; (d) refazer Gold; (e) validar checksums/contagens/saldos; (f) publicar versão validada.

## 14. Benchmark de ClickHouse (opcional para currículo)

Embora ClickHouse seja obrigatório, criar estudo demonstrativo com dataset inteiramente sintético: `100k`, `1M`, `10M`, `100M` transações e snapshots. Comparar em ClickHouse layouts `ORDER BY`, particionamento, compressão, projection e materialized views, sem inserir PostgreSQL no runtime. Medir p50/p95, leitura, inserts em lote, memória, CPU, custo de `FINAL`, rebuild de fatos e escala do storage. Se desejar comparação entre SGBDs, rodá-la **apenas como benchmark isolado**, sem transformar PostgreSQL em dependência do produto. Publicar metodologia e resultados reais medidos, não números estimados.

## 15. ADRs a registrar

1. ADR-001 Monorepo Python/TypeScript, uv, Ruff, Pytest, GitHub Actions.
2. ADR-002 ClickHouse como único SGBD; tradeoff OLAP × atualizações interativas.
3. ADR-003 Bronze em Lake de arquivos; Silver/Gold em ClickHouse; separação de estado reprocessável.
4. ADR-004 `LocalObjectStore` V1 com interface S3-compatible futura.
5. ADR-005 Append-only e leitura de última versão com semântica determinística.
6. ADR-006 Eventos manuais independentes de rebuild; classificação versionada.
7. ADR-007 dbt-clickhouse para SQL analítico; motor Python para cálculos financeiros complexos.
8. ADR-008 Pluggy somente leitura, cursor e paginação por endpoint, auditoria antes de ingestion.
9. ADR-009 IA local com Ollama, prompt não confiável e aprovação manual.
10. ADR-010 Sem Airflow ou outro metastore na V1.
11. ADR-011 Segurança por padrão, rede fechada, armazenamento e backup criptografados.
12. ADR-012 Política de desempenho, precisão financeira, dados ausentes e exposição econômica.
13. ADR-013 Dados sintéticos públicos e dados reais privados.

## 16. Prompt para iniciar a implementação com agente de código

> Você é o agente responsável por implementar, de maneira incremental, o projeto descrito em `docs/implementation-plan.md`. Leia o plano completo e execute **somente a Fase 0**. Não acesse a Pluggy nem solicite credenciais bancárias nesta fase. Entregue um monorepo modular usando Python/uv/Ruff/Pytest, ClickHouse como único SGBD, FastAPI mínimo, React/TypeScript mínimo, Docker Compose com redes privadas, scripts Windows PowerShell, migrações SQL e testes de segurança/infraestrutura com dados sintéticos. Crie ADRs, `docs/threat-model.md` e um README executável. Nenhum serviço sensível poderá ser publicado fora de localhost; nenhum segredo aparecerá em logs. Prepare uma interface para `LocalObjectStore`, mas implemente a persistência Bronze somente na Fase 1. Execute testes/lint, documente resultados e pendências e **pare ao terminar a Fase 0**, aguardando avaliação dos critérios de aceite antes de avançar.

## 17. Referências verificadas e pontos a revisar ao implementar

- Pluggy, paginação por cursor `v2` e por página em outros recursos: https://docs.pluggy.ai/en/reference/basic-concepts
- Pluggy, transações, IDs e reconexões: https://docs.pluggy.ai/en/docs/products/transactions
- ClickHouse, `ReplacingMergeTree` e `FINAL`: https://clickhouse.com/docs/guides/developer/replacing-merge-tree
- dbt ClickHouse setup/limitações da versão do adapter: https://docs.getdbt.com/docs/local/connect-data-platform/clickhouse-setup
- Ollama, `OLLAMA_NO_CLOUD`: https://github.com/ollama/ollama/blob/main/docs/faq.mdx

**Nota:** documentação, disponibilidade de campos Pluggy, versões do dbt adapter e opções de storage são mutáveis. Confirmar as versões e políticas antes de codificar; registrar no repositório as versões efetivamente testadas.
