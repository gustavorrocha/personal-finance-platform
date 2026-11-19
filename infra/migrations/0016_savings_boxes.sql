ALTER TABLE core.provider_versions
    ADD COLUMN IF NOT EXISTS name Nullable(String),
    ADD COLUMN IF NOT EXISTS issuer Nullable(String),
    ADD COLUMN IF NOT EXISTS indexer LowCardinality(Nullable(String)),
    ADD COLUMN IF NOT EXISTS rate_periodicity LowCardinality(Nullable(String)),
    ADD COLUMN IF NOT EXISTS rate_calculation LowCardinality(Nullable(String)),
    ADD COLUMN IF NOT EXISTS fixed_rate Nullable(Decimal(38, 12)),
    ADD COLUMN IF NOT EXISTS purchase_date Nullable(Date),
    ADD COLUMN IF NOT EXISTS original_amount Nullable(Decimal(38, 12)),
    ADD COLUMN IF NOT EXISTS withdrawal_amount Nullable(Decimal(38, 12)),
    ADD COLUMN IF NOT EXISTS income_tax Nullable(Decimal(38, 12)),
    ADD COLUMN IF NOT EXISTS iof Nullable(Decimal(38, 12)),
    ADD COLUMN IF NOT EXISTS fees Nullable(Decimal(38, 12)),
    ADD COLUMN IF NOT EXISTS net_amount Nullable(Decimal(38, 12)),
    ADD COLUMN IF NOT EXISTS movement_type LowCardinality(Nullable(String));

-- Every published savings-box observation, one per box and day, for return calculations.
CREATE VIEW IF NOT EXISTS analytics.savings_box_history
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT item_key,
       entity_key AS box_key,
       scope_id AS account_key,
       toDate(observed_at) AS observed_on,
       argMax(name, observed_at) AS name,
       argMax(currency, observed_at) AS currency,
       argMax(balance, observed_at) AS balance,
       argMax(rate, observed_at) * 100 AS indexer_percentage,
       argMax(fixed_rate, observed_at) AS fixed_rate,
       argMax(indexer, observed_at) AS indexer,
       max(observed_at) AS last_observed_at
FROM core.provider_versions FINAL
WHERE resource = 'savings_boxes'
  AND run_id IN (SELECT run_id FROM metadata.ingestion_publications)
GROUP BY item_key, box_key, account_key, observed_on;

-- Boxes reported in the latest observation of their account.
CREATE VIEW IF NOT EXISTS analytics.savings_boxes
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT *
FROM analytics.savings_box_history
WHERE (account_key, last_observed_at) IN (
    SELECT account_key, max(last_observed_at) FROM analytics.savings_box_history
    GROUP BY account_key
);

-- Positions plus savings boxes; savings boxes carry their own name and remuneration.
CREATE OR REPLACE VIEW analytics.investments_dashboard
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT item_key,
       entity_key AS position_key,
       if(match(ifNull(symbol, ''), '^[A-Z]{1,6}([0-9]{1,2})?([.][A-Z]{1,5})?$'),
          symbol, NULL) AS ticker,
       CAST(NULL, 'Nullable(String)') AS name,
       type AS position_type,
       subtype,
       status,
       currency,
       balance AS net_balance,
       amount AS gross_amount,
       quantity,
       unit_value AS unit_price,
       rate AS indexer_percentage,
       rate_type AS indexer,
       economic_date AS reference_date,
       due_date AS maturity_date,
       observed_at
FROM core.instrument_current
UNION ALL
SELECT item_key,
       box_key AS position_key,
       NULL AS ticker,
       name,
       'SAVINGS_BOX' AS position_type,
       NULL AS subtype,
       NULL AS status,
       currency,
       balance AS net_balance,
       balance AS gross_amount,
       NULL AS quantity,
       NULL AS unit_price,
       indexer_percentage,
       indexer,
       observed_on AS reference_date,
       NULL AS maturity_date,
       last_observed_at AS observed_at
FROM analytics.savings_boxes;

-- Savings-box movements name their box: "Dinheiro reservado <box>".
CREATE OR REPLACE VIEW analytics.investment_flows
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT t.item_key AS item_key,
       t.entity_key AS transaction_key,
       t.economic_date AS economic_date,
       t.currency AS currency,
       t.investment_kind AS kind,
       -- Contributions and withdrawals are positive; investment taxes reduce income.
       if(t.investment_kind = 'income' AND t.type = 'DEBIT', -abs(t.amount), abs(t.amount)) AS amount,
       trim(replaceRegexpOne(
           if(match(t.bank_description, '(?i)^dinheiro (reservado|retirado)'), t.bank_description, ''),
           '(?i)^dinheiro (reservado|retirado)', '')) AS savings_box
FROM
(
    SELECT item_key, entity_key, economic_date, currency, amount, type, status,
           investment_kind, bank_description, deleted
    FROM core.provider_versions FINAL
    WHERE resource = 'transactions'
      AND run_id IN (SELECT run_id FROM metadata.ingestion_publications)
    ORDER BY observed_at DESC, run_id DESC, row_order DESC
    LIMIT 1 BY item_key, entity_key
) AS t
WHERE NOT t.deleted AND t.status = 'POSTED'
    AND t.investment_kind IN ('contribution', 'withdrawal', 'income')
    AND t.economic_date IS NOT NULL AND t.currency IS NOT NULL AND t.amount IS NOT NULL;
