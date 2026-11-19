ALTER TABLE core.provider_versions
    ADD COLUMN IF NOT EXISTS reserved_balance Nullable(Decimal(38, 12));

-- Current invested money: reported positions plus balances reserved inside accounts.
CREATE VIEW IF NOT EXISTS analytics.invested_balances
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT item_key, currency, 'positions' AS source, balance,
       toDate(observed_at) AS observed_on
FROM core.instrument_current
WHERE NOT deleted AND currency IS NOT NULL AND balance IS NOT NULL
UNION ALL
SELECT a.item_key AS item_key, a.currency AS currency, 'savings_boxes' AS source,
       a.reserved_balance AS balance, toDate(a.observed_at) AS observed_on
FROM
(
    SELECT item_key, currency, reserved_balance, observed_at, deleted
    FROM core.provider_versions FINAL
    WHERE resource = 'accounts'
      AND run_id IN (SELECT run_id FROM metadata.ingestion_publications)
    ORDER BY observed_at DESC, run_id DESC, row_order DESC
    LIMIT 1 BY item_key, entity_key
) AS a
WHERE NOT a.deleted AND a.currency IS NOT NULL AND a.reserved_balance IS NOT NULL;
