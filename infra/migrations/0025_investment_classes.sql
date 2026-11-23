-- Editable investment classes, each position's class and the daily history of positions.
-- Class and assignment changes are append-only events; the latest event wins.
CREATE TABLE IF NOT EXISTS core.investment_classes
(
    class_id UUID,
    name String,
    archived Bool,
    changed_at DateTime64(6, 'UTC') DEFAULT now64(6),
    event_id UUID DEFAULT generateUUIDv4()
)
ENGINE = MergeTree
ORDER BY (class_id, changed_at, event_id);

-- position_key is a position's or a savings box's entity key. A zero class_id returns the
-- position to its automatic class.
CREATE TABLE IF NOT EXISTS core.investment_class_assignments
(
    position_key UUID,
    class_id UUID,
    changed_at DateTime64(6, 'UTC') DEFAULT now64(6),
    event_id UUID DEFAULT generateUUIDv4()
)
ENGINE = MergeTree
ORDER BY (position_key, changed_at, event_id);

INSERT INTO core.investment_classes (class_id, name, archived, changed_at) VALUES
    ('0aa43018-e7bd-5a63-99ba-c9b0c13ca31e', 'Renda fixa - Inflação', false, '2026-11-23 00:00:00'),
    ('443ce26b-6361-545f-9c5c-f7482f64d806', 'Renda fixa - CDI', false, '2026-11-23 00:00:00'),
    ('389552c8-5aaf-5acb-896a-29675e75711e', 'Renda fixa - Pré', false, '2026-11-23 00:00:00'),
    ('f79ee425-a7d3-5738-8f2b-f247971ca8e5', 'Cotas de fundos', false, '2026-11-23 00:00:00'),
    ('aab6e92b-c033-523b-a71f-3a5a48777d34', 'ETF renda fixa', false, '2026-11-23 00:00:00'),
    ('9c05e606-3497-536c-9480-5b3caa66d5ce', 'ETF ações', false, '2026-11-23 00:00:00');

CREATE VIEW IF NOT EXISTS analytics.investment_classes
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT class_id, name
FROM
(
    SELECT class_id,
           argMax(name, (changed_at, event_id)) AS name,
           argMax(archived, (changed_at, event_id)) AS archived
    FROM core.investment_classes
    GROUP BY class_id
)
WHERE NOT archived;

CREATE VIEW IF NOT EXISTS analytics.investment_class_assignments
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT position_key, class_id
FROM
(
    SELECT position_key, argMax(class_id, (changed_at, event_id)) AS class_id
    FROM core.investment_class_assignments
    GROUP BY position_key
)
WHERE class_id != toUUID('00000000-0000-0000-0000-000000000000');

-- One balance per position and day: the last one stored that day. Savings boxes included.
CREATE VIEW IF NOT EXISTS analytics.investment_position_history
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
       '' AS savings_box
FROM
(
    SELECT *
    FROM core.provider_versions FINAL
    WHERE resource = 'investments' AND NOT deleted AND balance IS NOT NULL
      AND currency IS NOT NULL
      AND run_id IN (SELECT run_id FROM metadata.ingestion_publications)
)
GROUP BY item_key, position_key, observed_on
UNION ALL
SELECT item_key, box_key, observed_on, 'SAVINGS_BOX', CAST(NULL, 'Nullable(String)'),
       indexer, fixed_rate, CAST(NULL, 'Nullable(String)'), name, currency, balance, name
FROM analytics.savings_box_history;

-- Purchases and sales of each position, as the provider reports them.
CREATE VIEW IF NOT EXISTS analytics.investment_position_movements
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT item_key, scope_id AS position_key, economic_date, type, amount
FROM
(
    SELECT item_key, entity_key, scope_id, economic_date, type, amount, deleted
    FROM core.provider_versions FINAL
    WHERE resource = 'investment_movements'
      AND run_id IN (SELECT run_id FROM metadata.ingestion_publications)
    ORDER BY observed_at DESC, run_id DESC, row_order DESC
    LIMIT 1 BY item_key, entity_key
)
WHERE NOT deleted AND type IN ('BUY', 'SELL') AND scope_id IS NOT NULL
  AND economic_date IS NOT NULL AND amount IS NOT NULL;
