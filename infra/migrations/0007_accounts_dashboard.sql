CREATE VIEW IF NOT EXISTS analytics.accounts_dashboard
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT item_key,
       entity_key AS account_key,
       type AS account_type,
       subtype,
       currency,
       balance,
       observed_at
FROM core.account_current;
