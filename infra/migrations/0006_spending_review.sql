CREATE TABLE IF NOT EXISTS core.spending_reviews
(
    item_key UUID,
    transaction_key UUID,
    decision LowCardinality(String),
    decided_at DateTime64(6, 'UTC') DEFAULT now64(6),
    event_id UUID DEFAULT generateUUIDv4(),
    CONSTRAINT valid_decision CHECK decision IN ('include', 'exclude', 'reset')
)
ENGINE = MergeTree
ORDER BY (item_key, transaction_key, decided_at, event_id);

CREATE VIEW IF NOT EXISTS analytics.spending_dashboard
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT t.item_key AS item_key,
       t.entity_key AS transaction_key,
       t.economic_date AS economic_date,
       t.currency AS currency,
       if(t.spending_kind = 'refund', -abs(t.amount), abs(t.amount)) AS net_amount,
       t.merchant_label AS merchant_label,
       t.merchant_key AS merchant_key,
       coalesce(nullIf(r.category, ''), nullIf(t.spending_category, ''), 'Uncategorized') AS category,
       ifNull(nullIf(d.decision, 'reset'), '') AS decision,
       multiIf(t.spending_kind = 'refund', true,
               d.decision = 'include', true, d.decision = 'exclude', false,
               t.spending_kind = 'purchase') AS included,
       t.spending_kind != 'refund'
           AND (t.spending_kind = 'review' OR d.decision IN ('include', 'exclude')) AS reviewable
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
LEFT JOIN
(
    SELECT item_key, transaction_key, argMax(decision, (decided_at, event_id)) AS decision
    FROM core.spending_reviews
    GROUP BY item_key, transaction_key
) AS d ON t.item_key = d.item_key AND t.entity_key = d.transaction_key
WHERE NOT t.deleted AND t.status = 'POSTED' AND t.spending_kind IN ('purchase', 'refund', 'review')
    AND t.economic_date IS NOT NULL AND t.currency IS NOT NULL AND t.amount IS NOT NULL;
