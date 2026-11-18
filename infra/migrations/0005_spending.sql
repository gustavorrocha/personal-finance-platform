ALTER TABLE core.provider_versions
    ADD COLUMN IF NOT EXISTS spending_kind LowCardinality(String),
    ADD COLUMN IF NOT EXISTS spending_category LowCardinality(String),
    ADD COLUMN IF NOT EXISTS merchant_label String,
    ADD COLUMN IF NOT EXISTS merchant_key String;

CREATE TABLE IF NOT EXISTS core.spending_rules
(
    item_key UUID,
    merchant_key String,
    category LowCardinality(String),
    changed_at DateTime64(6, 'UTC') DEFAULT now64(6),
    event_id UUID DEFAULT generateUUIDv4()
)
ENGINE = MergeTree
ORDER BY (item_key, merchant_key, changed_at, event_id);

CREATE VIEW IF NOT EXISTS analytics.spending_current
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT t.item_key AS item_key,
       t.entity_key AS transaction_key,
       t.economic_date AS economic_date,
       t.currency AS currency,
       if(t.spending_kind = 'refund', -abs(t.amount), abs(t.amount)) AS net_amount,
       t.merchant_label AS merchant_label,
       t.merchant_key AS merchant_key,
       coalesce(nullIf(r.category, ''), nullIf(t.spending_category, ''), 'Uncategorized') AS category
FROM
(
    SELECT *
    FROM core.provider_versions FINAL
    WHERE resource = 'transactions'
      AND run_id IN (SELECT run_id FROM metadata.ingestion_publications)
    ORDER BY observed_at DESC, run_id DESC, row_order DESC
    LIMIT 1 BY item_key, entity_key
) AS t
LEFT JOIN
(
    SELECT item_key, merchant_key, argMax(category, (changed_at, event_id)) AS category
    FROM core.spending_rules
    GROUP BY item_key, merchant_key
) AS r ON t.item_key = r.item_key AND t.merchant_key = r.merchant_key
WHERE NOT t.deleted AND t.status = 'POSTED' AND t.spending_kind IN ('purchase', 'refund')
    AND t.economic_date IS NOT NULL AND t.currency IS NOT NULL AND t.amount IS NOT NULL;
