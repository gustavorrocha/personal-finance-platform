-- Account and card details the provider reports, and accounts the operator disabled.
ALTER TABLE core.provider_versions
    ADD COLUMN IF NOT EXISTS number_suffix Nullable(String),
    ADD COLUMN IF NOT EXISTS brand LowCardinality(Nullable(String)),
    ADD COLUMN IF NOT EXISTS level LowCardinality(Nullable(String)),
    ADD COLUMN IF NOT EXISTS credit_limit Nullable(Decimal(38, 12)),
    ADD COLUMN IF NOT EXISTS available_credit Nullable(Decimal(38, 12)),
    ADD COLUMN IF NOT EXISTS minimum_payment Nullable(Decimal(38, 12)),
    ADD COLUMN IF NOT EXISTS close_date Nullable(Date);

CREATE TABLE IF NOT EXISTS core.account_settings
(
    item_key UUID,
    account_key UUID,
    disabled Bool,
    changed_at DateTime64(6, 'UTC') DEFAULT now64(6),
    event_id UUID DEFAULT generateUUIDv4()
)
ENGINE = MergeTree
ORDER BY (item_key, account_key, changed_at, event_id);

-- A disabled account leaves balances and spending; its data stays in the warehouse.
CREATE VIEW IF NOT EXISTS core.disabled_accounts AS
SELECT item_key, account_key
FROM core.account_settings
GROUP BY item_key, account_key
HAVING argMax(disabled, (changed_at, event_id));

CREATE OR REPLACE VIEW analytics.accounts_dashboard
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT a.item_key AS item_key,
       a.entity_key AS account_key,
       a.type AS account_type,
       a.subtype AS subtype,
       a.currency AS currency,
       a.balance AS balance,
       a.observed_at AS observed_at,
       a.name AS name,
       a.number_suffix AS number_suffix,
       a.brand AS brand,
       a.level AS level,
       a.credit_limit AS credit_limit,
       a.available_credit AS available_credit,
       a.minimum_payment AS minimum_payment,
       a.due_date AS due_date,
       a.close_date AS close_date,
       a.entity_key IN (SELECT account_key FROM core.disabled_accounts) AS disabled
FROM
(
    SELECT *
    FROM core.provider_versions FINAL
    WHERE resource = 'accounts'
      AND run_id IN (SELECT run_id FROM metadata.ingestion_publications)
    ORDER BY observed_at DESC, run_id DESC, row_order DESC
    LIMIT 1 BY item_key, entity_key
) AS a
WHERE NOT a.deleted;

-- Names a connection after its accounts, since an aggregator's connector name says
-- nothing about the bank: the shortest bank account name, else the shortest card name.
CREATE OR REPLACE VIEW analytics.connection_names
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT item_key, argMin(name, (account_type != 'BANK', length(name))) AS institution
FROM analytics.accounts_dashboard
WHERE name IS NOT NULL
GROUP BY item_key;

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
      AND (scope_id IS NULL OR scope_id NOT IN (SELECT account_key FROM core.disabled_accounts))
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
      AND (scope_id IS NULL OR scope_id NOT IN (SELECT account_key FROM core.disabled_accounts))
    ORDER BY observed_at DESC, run_id DESC, row_order DESC
    LIMIT 1 BY item_key, entity_key
) AS t
INNER JOIN core.credit_card_current AS a
    ON t.item_key = a.item_key AND t.scope_id = a.entity_key
WHERE NOT t.deleted AND t.status = 'PENDING' AND t.type = 'DEBIT'
    AND t.spending_kind = 'purchase'
    AND t.economic_date IS NOT NULL AND t.currency IS NOT NULL AND t.amount > 0;
