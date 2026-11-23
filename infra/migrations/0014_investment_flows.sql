ALTER TABLE core.provider_versions
    ADD COLUMN IF NOT EXISTS investment_kind LowCardinality(String);

CREATE VIEW IF NOT EXISTS analytics.investment_flows
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT t.item_key AS item_key,
       t.entity_key AS transaction_key,
       t.economic_date AS economic_date,
       t.currency AS currency,
       t.investment_kind AS kind,
       -- Contributions and withdrawals are positive; investment taxes reduce income.
       if(t.investment_kind = 'income' AND t.type = 'DEBIT', -abs(t.amount), abs(t.amount)) AS amount
FROM
(
    SELECT item_key, entity_key, economic_date, currency, amount, type, status,
           investment_kind, deleted
    FROM core.provider_versions FINAL
    WHERE resource = 'transactions'
      AND run_id IN (SELECT run_id FROM metadata.ingestion_publications)
    ORDER BY observed_at DESC, run_id DESC, row_order DESC
    LIMIT 1 BY item_key, entity_key
) AS t
WHERE NOT t.deleted AND t.status = 'POSTED'
    AND t.investment_kind IN ('contribution', 'withdrawal', 'income')
    AND t.economic_date IS NOT NULL AND t.currency IS NOT NULL AND t.amount IS NOT NULL;
