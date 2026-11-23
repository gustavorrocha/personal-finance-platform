-- A category can be set for one transaction only, e.g. a PIX to a person, without
-- changing every expense from the same merchant. It wins over every other rule.
ALTER TABLE core.category_rules DROP CONSTRAINT IF EXISTS valid_scope;
ALTER TABLE core.category_rules ADD CONSTRAINT valid_scope
    CHECK scope IN ('transaction', 'merchant', 'mcc', 'provider');

CREATE OR REPLACE VIEW analytics.provider_spending
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT t.item_key AS item_key,
       t.entity_key AS transaction_key,
       t.economic_date AS economic_date,
       t.currency AS currency,
       if(toString(t.spending_kind) IN ('refund', 'reimbursable'), -abs(t.amount), abs(t.amount)) AS net_amount,
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
       t.category_id AS provider_category_id,
       t.mcc AS mcc,
       if(t.merchant_cnpj != '', t.merchant_cnpj, t.counterparty_cnpj) AS cnpj,
       t.merchant_cnae AS cnae,
       if(t.merchant_business_name != '', t.merchant_business_name, t.counterparty_name) AS business_name,
       t.merchant_category AS merchant_category,
       if(c.is_card, 'card', 'bank') AS source,
       dictGetOrDefault('core.category_rule_dict', ('category_id', 'category', 'subcategory'), ('transaction', concat(toString(t.item_key), ':', toString(t.entity_key))), ('', '', '')) AS transaction_rule,
       dictGetOrDefault('core.category_rule_dict', ('category_id', 'category', 'subcategory'), ('merchant', t.merchant_key), ('', '', '')) AS merchant_rule,
       dictGetOrDefault('core.category_rule_dict', ('category_id', 'category', 'subcategory'), ('provider', t.category_id), ('', '', '')) AS provider_rule,
       dictGetOrDefault('core.category_rule_dict', ('category_id', 'category', 'subcategory'), ('mcc', ifNull(toString(t.mcc), '')), ('', '', '')) AS mcc_rule,
       dictGetOrDefault('core.category_rule_dict', ('category_id', 'category', 'subcategory'), ('provider', concat(substring(t.category_id, 1, 2), '000000')), ('', '', '')) AS group_rule,
       multiIf(
           transaction_rule.1 != '', ('transaction', transaction_rule),
           merchant_rule.1 != '', ('merchant', merchant_rule),
           provider_rule.1 != '' AND NOT endsWith(t.category_id, '000000'),
               ('provider', provider_rule),
           mcc_rule.1 != '', ('mcc', mcc_rule),
           provider_rule.1 != '', ('provider', provider_rule),
           group_rule.1 != '', ('provider', group_rule),
           ('', ('', '', ''))) AS chosen_category,
       chosen_category.2.2 AS category,
       chosen_category.2.3 AS subcategory,
       chosen_category.2.1 AS category_id,
       chosen_category.1 AS category_rule,
       ifNull(nullIf(d.decision, 'reset'), '') AS decision,
       multiIf(t.spending_kind = 'refund', true,
               d.decision = 'include', true, d.decision = 'exclude', false,
               t.spending_kind = 'purchase') AS included,
       toString(t.spending_kind) NOT IN ('refund', 'reimbursable')
           AND (t.spending_kind = 'review' OR d.decision IN ('include', 'exclude')) AS reviewable,
       CAST(t.spending_kind = 'reimbursable', 'Bool') AS reimbursable
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
    SELECT DISTINCT item_key, entity_key, true AS is_card FROM core.credit_card_current
) AS c ON t.item_key = c.item_key AND t.scope_id = c.entity_key
LEFT JOIN
(
    SELECT item_key, transaction_key, argMax(decision, (decided_at, event_id)) AS decision
    FROM core.spending_reviews
    GROUP BY item_key, transaction_key
) AS d ON t.item_key = d.item_key AND t.entity_key = d.transaction_key
WHERE NOT t.deleted AND t.status = 'POSTED' AND t.spending_kind IN ('purchase', 'refund', 'review', 'reimbursable')
    AND t.economic_date IS NOT NULL AND t.currency IS NOT NULL AND t.amount IS NOT NULL;

CREATE OR REPLACE VIEW analytics.spending_dashboard
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT item_key,
       transaction_key,
       economic_date,
       currency,
       net_amount,
       merchant_label,
       operation,
       description,
       bank_category,
       transaction_time,
       original_purchase_date,
       installment_number,
       total_installments,
       installment_total_amount,
       merchant_key,
       provider_category_id,
       mcc,
       cnpj,
       cnae,
       business_name,
       merchant_category,
       source,
       category,
       subcategory,
       category_id,
       category_rule,
       decision,
       included,
       reviewable,
       reimbursable
FROM analytics.provider_spending
UNION ALL
SELECT item_key,
       transaction_key,
       economic_date,
       currency,
       net_amount,
       merchant_label,
       operation,
       description,
       bank_category,
       transaction_time,
       original_purchase_date,
       installment_number,
       total_installments,
       installment_total_amount,
       merchant_key,
       provider_category_id,
       mcc,
       cnpj,
       cnae,
       business_name,
       merchant_category,
       source,
       category,
       subcategory,
       category_id,
       category_rule,
       decision,
       included,
       reviewable,
       reimbursable
FROM
(
SELECT e.item_key AS item_key,
       e.transaction_key AS transaction_key,
       e.economic_date AS economic_date,
       e.currency AS currency,
       e.net_amount AS net_amount,
       e.merchant_label AS merchant_label,
       e.operation AS operation,
       '' AS description,
       '' AS bank_category,
       CAST(NULL, 'Nullable(DateTime64(6, \'UTC\'))') AS transaction_time,
       CAST(NULL, 'Nullable(Date)') AS original_purchase_date,
       CAST(NULL, 'Nullable(UInt16)') AS installment_number,
       CAST(NULL, 'Nullable(UInt16)') AS total_installments,
       CAST(NULL, 'Nullable(Decimal(38, 12))') AS installment_total_amount,
       e.merchant_key AS merchant_key,
       '' AS provider_category_id,
       CAST(NULL, 'Nullable(UInt16)') AS mcc,
       e.cnpj AS cnpj,
       '' AS cnae,
       '' AS business_name,
       '' AS merchant_category,
       'bank' AS source,
       dictGetOrDefault('core.category_rule_dict', ('category_id', 'category', 'subcategory'), ('transaction', concat(toString(e.item_key), ':', toString(e.transaction_key))), ('', '', '')) AS transaction_rule,
       dictGetOrDefault('core.category_rule_dict', ('category_id', 'category', 'subcategory'), ('merchant', e.merchant_key), ('', '', '')) AS merchant_rule,
       dictGetOrDefault('core.category_rule_dict', ('category_id', 'category', 'subcategory'), ('category', e.assigned_category), ('', '', '')) AS assigned_rule,
       multiIf(transaction_rule.1 != '', ('transaction', transaction_rule),
               merchant_rule.1 != '', ('merchant', merchant_rule),
               assigned_rule.1 != '', ('manual', assigned_rule),
               ('', ('', '', ''))) AS chosen_category,
       chosen_category.2.2 AS category,
       chosen_category.2.3 AS subcategory,
       chosen_category.2.1 AS category_id,
       chosen_category.1 AS category_rule,
       ifNull(nullIf(d.decision, 'reset'), '') AS decision,
       multiIf(d.decision = 'include', true, d.decision = 'exclude', false,
               e.kind = 'purchase') AS included,
       e.kind = 'review' OR d.decision IN ('include', 'exclude') AS reviewable,
       false AS reimbursable
FROM analytics.extra_spending AS e
LEFT JOIN
(
    SELECT item_key, transaction_key, argMax(decision, (decided_at, event_id)) AS decision
    FROM core.spending_reviews
    GROUP BY item_key, transaction_key
) AS d ON e.item_key = d.item_key AND e.transaction_key = d.transaction_key
);
