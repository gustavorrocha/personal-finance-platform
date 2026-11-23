-- Public daily prices of whole markets (Tesouro Direto redemption prices first), keyed by
-- source and asset. Re-downloadable reference data: a later download of a day wins.
CREATE TABLE IF NOT EXISTS core.market_prices
(
    source LowCardinality(String),
    asset String,
    day Date,
    price Decimal(38, 8),
    fetched_at DateTime64(6, 'UTC') DEFAULT now64(6)
)
ENGINE = ReplacingMergeTree(fetched_at)
ORDER BY (source, asset, day);

CREATE VIEW IF NOT EXISTS analytics.market_prices
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT source, asset, day, argMax(price, fetched_at) AS price
FROM core.market_prices
GROUP BY source, asset, day;

-- Files already downloaded for a set of held assets, so later runs skip them; a new holding
-- changes the set and fetches its history again.
CREATE TABLE IF NOT EXISTS core.market_downloads
(
    source LowCardinality(String),
    file String,
    assets String,
    fetched_at DateTime64(6, 'UTC') DEFAULT now64(6)
)
ENGINE = ReplacingMergeTree(fetched_at)
ORDER BY (source, assets, file);

-- Adds the due date, ISIN and quantity, which identify a position's market prices.
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
       argMax(gross_balance, observed_at) AS gross,
       argMax(due_date, observed_at) AS due_date,
       argMax(isin, observed_at) AS isin,
       argMax(quantity, observed_at) AS quantity
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
       indexer_percentage, CAST(NULL, 'Nullable(Date)'), balance, CAST(NULL, 'Nullable(Date)'),
       CAST(NULL, 'Nullable(String)'), CAST(NULL, 'Nullable(Decimal(38, 12))')
FROM analytics.savings_box_history;
