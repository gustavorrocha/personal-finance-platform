-- Spending the provider does not report as transactions: payments made straight from a
-- savings-box balance, and manual or recurring entries such as rent.

-- One-off and recurring manual expenses. Append-only events; the latest one wins.
-- A one-off entry has end_month = start_month. With a CNPJ, a month that already has a
-- reported payment to that CNPJ skips the entry, so the same bill never counts twice.
CREATE TABLE IF NOT EXISTS core.manual_expenses
(
    entry_id UUID,
    item_key UUID,
    description String,
    amount Decimal(38, 12),
    currency LowCardinality(String),
    category_id UUID,
    day_of_month UInt8,
    start_month Date,
    end_month Nullable(Date),
    cnpj String,
    archived Bool,
    changed_at DateTime64(6, 'UTC') DEFAULT now64(6),
    event_id UUID DEFAULT generateUUIDv4()
)
ENGINE = MergeTree
ORDER BY (entry_id, changed_at, event_id);

CREATE VIEW IF NOT EXISTS analytics.manual_expenses
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT *
FROM
(
    SELECT entry_id,
           argMax(item_key, (changed_at, event_id)) AS item_key,
           argMax(description, (changed_at, event_id)) AS description,
           argMax(amount, (changed_at, event_id)) AS amount,
           argMax(currency, (changed_at, event_id)) AS currency,
           argMax(category_id, (changed_at, event_id)) AS category_id,
           argMax(day_of_month, (changed_at, event_id)) AS day_of_month,
           argMax(start_month, (changed_at, event_id)) AS start_month,
           argMax(end_month, (changed_at, event_id)) AS end_month,
           argMax(cnpj, (changed_at, event_id)) AS cnpj,
           argMax(archived, (changed_at, event_id)) AS archived
    FROM core.manual_expenses
    GROUP BY entry_id
)
WHERE NOT archived;

-- Categories can be looked up by their own id ('category' scope) for manual entries.
CREATE OR REPLACE VIEW core.category_rule_current
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT r.scope AS scope,
       r.rule_key AS rule_key,
       toString(c.category_id) AS category_id,
       if(c.parent_id = toUUID('00000000-0000-0000-0000-000000000000'), c.name, p.name) AS category,
       if(c.parent_id = toUUID('00000000-0000-0000-0000-000000000000'), '', c.name) AS subcategory
FROM
(
    SELECT scope, rule_key, argMax(category_id, (changed_at, event_id)) AS category_id
    FROM core.category_rules
    GROUP BY scope, rule_key
    UNION ALL
    SELECT 'category', toString(category_id), category_id FROM analytics.spending_categories
) AS r
INNER JOIN analytics.spending_categories AS c ON r.category_id = c.category_id
LEFT JOIN analytics.spending_categories AS p ON c.parent_id = p.category_id;

SYSTEM RELOAD DICTIONARY core.category_rule_dict;

-- Money that left a savings box between two balance observations without a reported
-- withdrawal: balance before + reported contributions - reported withdrawals - balance after.
-- Yield raises the balance, so it can only hide small outflows, never invent them.
CREATE VIEW IF NOT EXISTS analytics.savings_box_outflows
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
WITH boxes AS
(
    SELECT DISTINCT item_key, box_key, account_key, lower(name) AS box, currency
    FROM analytics.savings_box_history
),
events AS
(
    SELECT item_key, box_key, observed_on AS day, 1 AS observation, balance,
           toDecimal128(0, 12) AS flow, name
    FROM analytics.savings_box_history
    UNION ALL
    SELECT b.item_key, b.box_key, f.day, 0, NULL, f.flow, ''
    FROM
    (
        SELECT item_key, lower(savings_box) AS box, economic_date AS day,
               toDecimal128(sum(if(kind = 'contribution', amount, -amount)), 12) AS flow
        FROM analytics.investment_flows
        WHERE savings_box != ''
        GROUP BY item_key, box, day
    ) AS f
    INNER JOIN boxes AS b ON f.item_key = b.item_key AND f.box = b.box
),
running AS
(
    SELECT *,
           sum(flow) OVER (PARTITION BY box_key ORDER BY day, observation
                           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative
    FROM events
),
observed AS
(
    SELECT item_key, box_key, name, day, balance, cumulative,
           lagInFrame(balance) OVER w AS previous_balance,
           lagInFrame(cumulative) OVER w AS previous_cumulative,
           lagInFrame(day) OVER w AS previous_day,
           row_number() OVER w AS position
    FROM running
    WHERE observation = 1
    WINDOW w AS (PARTITION BY box_key ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
)
SELECT o.item_key AS item_key,
       o.box_key AS box_key,
       reinterpretAsUUID(MD5(concat('savings-box-outflow:', toString(o.box_key), ':', toString(o.day)))) AS transaction_key,
       o.name AS name,
       b.currency AS currency,
       o.previous_day AS previous_day,
       o.day AS economic_date,
       o.previous_balance + (o.cumulative - o.previous_cumulative) - o.balance AS amount
FROM observed AS o
INNER JOIN boxes AS b ON o.box_key = b.box_key
WHERE o.position > 1 AND amount >= 1;

CREATE OR REPLACE VIEW analytics.provider_spending
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
       t.category_id AS provider_category_id,
       t.mcc AS mcc,
       if(t.merchant_cnpj != '', t.merchant_cnpj, t.counterparty_cnpj) AS cnpj,
       t.merchant_cnae AS cnae,
       if(t.merchant_business_name != '', t.merchant_business_name, t.counterparty_name) AS business_name,
       t.merchant_category AS merchant_category,
       if(c.is_card, 'card', 'bank') AS source,
       dictGetOrDefault('core.category_rule_dict', ('category_id', 'category', 'subcategory'), ('merchant', t.merchant_key), ('', '', '')) AS merchant_rule,
       dictGetOrDefault('core.category_rule_dict', ('category_id', 'category', 'subcategory'), ('provider', t.category_id), ('', '', '')) AS provider_rule,
       dictGetOrDefault('core.category_rule_dict', ('category_id', 'category', 'subcategory'), ('mcc', ifNull(toString(t.mcc), '')), ('', '', '')) AS mcc_rule,
       dictGetOrDefault('core.category_rule_dict', ('category_id', 'category', 'subcategory'), ('provider', concat(substring(t.category_id, 1, 2), '000000')), ('', '', '')) AS group_rule,
       multiIf(
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
    SELECT DISTINCT item_key, entity_key, true AS is_card FROM core.credit_card_current
) AS c ON t.item_key = c.item_key AND t.scope_id = c.entity_key
LEFT JOIN
(
    SELECT item_key, transaction_key, argMax(decision, (decided_at, event_id)) AS decision
    FROM core.spending_reviews
    GROUP BY item_key, transaction_key
) AS d ON t.item_key = d.item_key AND t.entity_key = d.transaction_key
WHERE NOT t.deleted AND t.status = 'POSTED' AND t.spending_kind IN ('purchase', 'refund', 'review')
    AND t.economic_date IS NOT NULL AND t.currency IS NOT NULL AND t.amount IS NOT NULL;

-- Box outflows wait in Debit review; manual entries count as soon as they occur.
CREATE VIEW IF NOT EXISTS analytics.extra_spending
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT item_key, transaction_key, economic_date, currency, amount AS net_amount,
       name AS merchant_label, 'SAVINGS_BOX' AS operation,
       lower(hex(SHA256(concat('savings-box:', lower(name))))) AS merchant_key,
       '' AS cnpj, 'review' AS kind, '' AS assigned_category
FROM analytics.savings_box_outflows
UNION ALL
SELECT item_key,
       reinterpretAsUUID(MD5(concat('manual-expense:', toString(entry_id), ':', toString(month)))),
       occurs_on, currency, amount, description, 'MANUAL',
       lower(hex(SHA256(concat('manual:', toString(entry_id))))),
       cnpj, 'purchase',
       if(category_id = toUUID('00000000-0000-0000-0000-000000000000'), '', toString(category_id))
FROM
(
    SELECT m.*,
           addMonths(m.start_month, step) AS month,
           makeDate(toYear(month), toMonth(month),
                    least(m.day_of_month, toDayOfMonth(toLastDayOfMonth(month)))) AS occurs_on
    FROM analytics.manual_expenses AS m
    ARRAY JOIN range(toUInt32(greatest(0, dateDiff('month', m.start_month,
        least(ifNull(m.end_month, toStartOfMonth(today())), toStartOfMonth(today()))) + 1))) AS step
)
WHERE occurs_on <= today()
  AND (cnpj = ''
       OR (cnpj, toStartOfMonth(occurs_on)) NOT IN
          (SELECT cnpj, toStartOfMonth(economic_date) FROM analytics.provider_spending
           WHERE cnpj != '' AND net_amount > 0));

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
       reviewable
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
       reviewable
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
       dictGetOrDefault('core.category_rule_dict', ('category_id', 'category', 'subcategory'), ('merchant', e.merchant_key), ('', '', '')) AS merchant_rule,
       dictGetOrDefault('core.category_rule_dict', ('category_id', 'category', 'subcategory'), ('category', e.assigned_category), ('', '', '')) AS assigned_rule,
       multiIf(merchant_rule.1 != '', ('merchant', merchant_rule),
               assigned_rule.1 != '', ('manual', assigned_rule),
               ('', ('', '', ''))) AS chosen_category,
       chosen_category.2.2 AS category,
       chosen_category.2.3 AS subcategory,
       chosen_category.2.1 AS category_id,
       chosen_category.1 AS category_rule,
       ifNull(nullIf(d.decision, 'reset'), '') AS decision,
       multiIf(d.decision = 'include', true, d.decision = 'exclude', false,
               e.kind = 'purchase') AS included,
       e.kind = 'review' OR d.decision IN ('include', 'exclude') AS reviewable
FROM analytics.extra_spending AS e
LEFT JOIN
(
    SELECT item_key, transaction_key, argMax(decision, (decided_at, event_id)) AS decision
    FROM core.spending_reviews
    GROUP BY item_key, transaction_key
) AS d ON e.item_key = d.item_key AND e.transaction_key = d.transaction_key
);
