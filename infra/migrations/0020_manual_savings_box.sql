-- A manual entry can name the savings box that paid it. Each occurrence then counts as
-- a withdrawal from that box, so box balances, outflow detection and invested-wealth
-- estimates agree with money that left the box without a reported transaction.
ALTER TABLE core.manual_expenses ADD COLUMN IF NOT EXISTS savings_box String;

CREATE OR REPLACE VIEW analytics.manual_expenses
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
           argMax(savings_box, (changed_at, event_id)) AS savings_box,
           argMax(archived, (changed_at, event_id)) AS archived
    FROM core.manual_expenses
    GROUP BY entry_id
)
WHERE NOT archived;

-- One row per month a manual entry occurs. With a CNPJ, a month that already has a
-- reported payment to that CNPJ is skipped.
CREATE VIEW IF NOT EXISTS analytics.manual_occurrences
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT item_key,
       entry_id,
       reinterpretAsUUID(MD5(concat('manual-expense:', toString(entry_id), ':', toString(month)))) AS transaction_key,
       occurs_on AS economic_date,
       currency,
       amount,
       description,
       cnpj,
       savings_box,
       category_id
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
    AND t.economic_date IS NOT NULL AND t.currency IS NOT NULL AND t.amount IS NOT NULL
UNION ALL
SELECT item_key, transaction_key, economic_date, currency, 'withdrawal' AS kind,
       amount, savings_box
FROM analytics.manual_occurrences
WHERE savings_box != '';

CREATE OR REPLACE VIEW analytics.extra_spending
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT item_key, transaction_key, economic_date, currency, amount AS net_amount,
       name AS merchant_label, 'SAVINGS_BOX' AS operation,
       lower(hex(SHA256(concat('savings-box:', lower(name))))) AS merchant_key,
       '' AS cnpj, 'review' AS kind, '' AS assigned_category
FROM analytics.savings_box_outflows
UNION ALL
SELECT item_key, transaction_key, economic_date, currency, amount, description, 'MANUAL',
       lower(hex(SHA256(concat('manual:', toString(entry_id))))),
       cnpj, 'purchase',
       if(category_id = toUUID('00000000-0000-0000-0000-000000000000'), '', toString(category_id))
FROM analytics.manual_occurrences;
