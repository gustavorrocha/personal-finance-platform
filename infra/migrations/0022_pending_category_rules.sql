-- Pending card purchases already count in the month: their category can be changed like
-- any other expense, including a rule for that single transaction.
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
       t.merchant_key AS merchant_key,
       t.category_id AS provider_category_id,
       t.mcc AS mcc,
       if(t.merchant_cnpj != '', t.merchant_cnpj, t.counterparty_cnpj) AS cnpj,
       t.merchant_cnae AS cnae,
       if(t.merchant_business_name != '', t.merchant_business_name, t.counterparty_name) AS business_name,
       t.merchant_category AS merchant_category,
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
       t.amount AS amount
FROM
(
    SELECT item_key, entity_key, scope_id, economic_date, currency, amount,
           type, status, spending_kind, deleted, merchant_label, bank_description, bank_category,
           transaction_time, original_purchase_date, installment_number, total_installments,
           installment_total_amount, spending_category, mcc, merchant_cnpj, counterparty_cnpj,
           merchant_cnae, merchant_business_name, counterparty_name, merchant_category,
           merchant_key, category_id
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
