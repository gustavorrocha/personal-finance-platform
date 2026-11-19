ALTER TABLE core.provider_versions
    ADD COLUMN IF NOT EXISTS bank_description String,
    ADD COLUMN IF NOT EXISTS bank_category String,
    ADD COLUMN IF NOT EXISTS transaction_time Nullable(DateTime64(6, 'UTC')),
    ADD COLUMN IF NOT EXISTS original_purchase_date Nullable(Date),
    ADD COLUMN IF NOT EXISTS installment_number Nullable(UInt16),
    ADD COLUMN IF NOT EXISTS total_installments Nullable(UInt16),
    ADD COLUMN IF NOT EXISTS installment_total_amount Nullable(Decimal(38, 12));

CREATE OR REPLACE VIEW analytics.spending_dashboard
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT t.item_key AS item_key,
       t.entity_key AS transaction_key,
       t.economic_date AS economic_date,
       t.currency AS currency,
       if(t.spending_kind = 'refund', -abs(t.amount), abs(t.amount)) AS net_amount,
       t.merchant_label AS merchant_label,
       t.spending_operation AS operation,
       t.bank_description AS description,
       t.bank_category AS bank_category,
       t.transaction_time AS transaction_time,
       t.original_purchase_date AS original_purchase_date,
       t.installment_number AS installment_number,
       t.total_installments AS total_installments,
       t.installment_total_amount AS installment_total_amount,
       t.merchant_key AS merchant_key,
       coalesce(nullIf(r.category, ''), nullIf(t.bank_category, ''), nullIf(t.spending_category, ''), 'Uncategorized') AS category,
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

CREATE OR REPLACE VIEW analytics.pending_card_spending
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT t.item_key AS item_key,
       t.economic_date AS economic_date,
       t.currency AS currency,
       t.bank_description AS description,
       t.bank_category AS bank_category,
       t.transaction_time AS transaction_time,
       t.original_purchase_date AS original_purchase_date,
       t.installment_number AS installment_number,
       t.total_installments AS total_installments,
       t.installment_total_amount AS installment_total_amount,
       t.entity_key AS transaction_key,
       t.merchant_label AS merchant_label,
       coalesce(nullIf(t.bank_category, ''), nullIf(t.spending_category, ''), 'Uncategorized') AS category,
       t.amount AS amount
FROM
(
    SELECT item_key, entity_key, scope_id, economic_date, currency, amount,
           type, status, spending_kind, deleted, merchant_label, bank_description, bank_category,
           transaction_time, original_purchase_date, installment_number, total_installments,
           installment_total_amount, spending_category
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
