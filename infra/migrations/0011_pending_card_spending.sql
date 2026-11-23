CREATE VIEW IF NOT EXISTS analytics.pending_card_spending
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT t.item_key AS item_key,
       t.economic_date AS economic_date,
       t.currency AS currency,
       t.amount AS amount
FROM
(
    SELECT item_key, entity_key, scope_id, economic_date, currency, amount,
           type, status, spending_kind, deleted
    FROM core.provider_versions FINAL
    WHERE resource = 'transactions'
      AND run_id IN (SELECT run_id FROM metadata.ingestion_publications)
    ORDER BY observed_at DESC, run_id DESC, row_order DESC
    LIMIT 1 BY item_key, entity_key
) AS t
INNER JOIN core.credit_card_current AS a
    ON t.item_key = a.item_key AND t.scope_id = a.entity_key
WHERE NOT t.deleted AND t.status = 'PENDING' AND t.type = 'DEBIT'
    AND t.spending_kind = 'purchase'
    AND t.economic_date IS NOT NULL AND t.currency IS NOT NULL AND t.amount > 0;
