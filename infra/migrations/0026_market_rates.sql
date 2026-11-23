-- Public daily rates from the Banco Central (SGS): CDI (12), Selic (11), IPCA (433).
-- Re-downloadable reference data, not provider captures: a later download of a day wins.
CREATE TABLE IF NOT EXISTS core.market_rates
(
    series LowCardinality(String),
    day Date,
    value Decimal(18, 8),
    fetched_at DateTime64(6, 'UTC') DEFAULT now64(6)
)
ENGINE = ReplacingMergeTree(fetched_at)
ORDER BY (series, day);

CREATE VIEW IF NOT EXISTS analytics.market_rates
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT series, day, argMax(value, fetched_at) AS value
FROM core.market_rates
GROUP BY series, day;

-- Adds what daily valuation needs: the indexer percentage, purchase date and the gross
-- balance (income tax and IOF withheld on redemption added back).
CREATE OR REPLACE VIEW analytics.investment_position_history
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT item_key,
       entity_key AS position_key,
       toDate(observed_at) AS observed_on,
       argMax(type, observed_at) AS type,
       argMax(subtype, observed_at) AS subtype,
       argMax(rate_type, observed_at) AS indexer,
       argMax(fixed_rate, observed_at) AS fixed_rate,
       argMax(symbol, observed_at) AS symbol,
       argMax(name, observed_at) AS name,
       argMax(currency, observed_at) AS currency,
       argMax(balance, observed_at) AS balance,
       '' AS savings_box,
       argMax(rate, observed_at) AS rate,
       argMax(purchase_date, observed_at) AS purchase_date,
       argMax(gross_balance, observed_at) AS gross
FROM
(
    SELECT *, balance + ifNull(income_tax, 0) + ifNull(iof, 0) AS gross_balance
    FROM core.provider_versions FINAL
    WHERE resource = 'investments' AND NOT deleted AND balance IS NOT NULL
      AND currency IS NOT NULL
      AND run_id IN (SELECT run_id FROM metadata.ingestion_publications)
)
GROUP BY item_key, position_key, observed_on
UNION ALL
SELECT item_key, box_key, observed_on, 'SAVINGS_BOX', CAST(NULL, 'Nullable(String)'),
       indexer, fixed_rate, CAST(NULL, 'Nullable(String)'), name, currency, balance, name,
       indexer_percentage, CAST(NULL, 'Nullable(Date)'), balance
FROM analytics.savings_box_history;
