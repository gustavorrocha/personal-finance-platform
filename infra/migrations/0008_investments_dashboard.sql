CREATE VIEW IF NOT EXISTS analytics.investments_dashboard
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT item_key,
       entity_key AS position_key,
       if(match(ifNull(symbol, ''), '^[A-Z]{1,6}([0-9]{1,2})?([.][A-Z]{1,5})?$'),
          symbol, NULL) AS ticker,
       type AS position_type,
       subtype,
       status,
       currency,
       balance AS net_balance,
       amount AS gross_amount,
       quantity,
       unit_value AS unit_price,
       economic_date AS reference_date,
       due_date AS maturity_date,
       observed_at
FROM core.instrument_current;
