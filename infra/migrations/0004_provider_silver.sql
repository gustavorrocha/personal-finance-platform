-- The optional GUI reader already has grants on the synthetic Bronze index.
CREATE TABLE IF NOT EXISTS metadata.provider_bronze_objects AS metadata.bronze_objects;

CREATE VIEW IF NOT EXISTS metadata.provider_bronze_objects_current AS
SELECT * FROM metadata.provider_bronze_objects FINAL;

CREATE TABLE IF NOT EXISTS metadata.ingestion_run_events
(
    run_id UUID,
    item_key UUID,
    event LowCardinality(String),
    recorded_at DateTime64(6, 'UTC')
)
ENGINE = MergeTree
ORDER BY (run_id, recorded_at, event);

-- One append publishes the entire run and, for successful syncs, its checkpoint.
CREATE TABLE IF NOT EXISTS metadata.ingestion_publications
(
    run_id UUID,
    item_key UUID,
    observed_at DateTime64(6, 'UTC'),
    kind LowCardinality(String),
    accounts Array(UUID),
    record_count UInt64
)
ENGINE = ReplacingMergeTree
ORDER BY run_id;

CREATE VIEW IF NOT EXISTS metadata.sync_checkpoints_current AS
SELECT item_key,
       tupleElement(latest, 1) AS observed_at,
       tupleElement(latest, 2) AS accounts
FROM
(
    SELECT item_key, argMax(tuple(observed_at, accounts), tuple(observed_at, run_id)) AS latest
    FROM metadata.ingestion_publications FINAL
    WHERE kind IN ('full', 'incremental')
    GROUP BY item_key
);

CREATE TABLE IF NOT EXISTS core.provider_versions
(
    run_id UUID,
    object_id UUID,
    record_id UUID,
    row_order UInt64,
    item_key UUID,
    resource LowCardinality(String),
    entity_key UUID,
    scope_id Nullable(UUID),
    observed_at DateTime64(6, 'UTC'),
    economic_date Nullable(Date),
    due_date Nullable(Date),
    trade_date Nullable(Date),
    issue_date Nullable(Date),
    consent_expires_at Nullable(DateTime64(6, 'UTC')),
    connector_id Nullable(UInt32),
    type LowCardinality(Nullable(String)),
    subtype LowCardinality(Nullable(String)),
    status LowCardinality(Nullable(String)),
    currency LowCardinality(Nullable(String)),
    amount Nullable(Decimal(38, 12)),
    balance Nullable(Decimal(38, 12)),
    quantity Nullable(Decimal(38, 12)),
    unit_value Nullable(Decimal(38, 12)),
    rate Nullable(Decimal(38, 12)),
    rate_type LowCardinality(Nullable(String)),
    symbol Nullable(String),
    isin Nullable(String),
    deleted Bool
)
ENGINE = ReplacingMergeTree
ORDER BY (resource, item_key, entity_key, run_id, record_id);

CREATE VIEW IF NOT EXISTS core.provider_observations AS
SELECT *
FROM core.provider_versions FINAL
WHERE run_id IN (SELECT run_id FROM metadata.ingestion_publications);

CREATE VIEW IF NOT EXISTS core.provider_current AS
SELECT *
FROM
(
    SELECT *
    FROM core.provider_observations
    ORDER BY observed_at DESC, run_id DESC, row_order DESC
    LIMIT 1 BY resource, item_key, entity_key
)
WHERE NOT deleted;

CREATE VIEW IF NOT EXISTS core.connection_current AS
SELECT * FROM core.provider_current WHERE resource = 'items';

CREATE VIEW IF NOT EXISTS core.institution_observations AS
SELECT DISTINCT connector_id, run_id, observed_at
FROM core.provider_observations WHERE resource = 'items' AND connector_id IS NOT NULL;

CREATE VIEW IF NOT EXISTS core.resource_current AS
SELECT * FROM core.provider_current WHERE resource = 'resources';

CREATE VIEW IF NOT EXISTS core.account_current AS
SELECT * FROM core.provider_current WHERE resource = 'accounts';

CREATE VIEW IF NOT EXISTS core.credit_card_current AS
SELECT * FROM core.account_current WHERE type = 'CREDIT';

CREATE VIEW IF NOT EXISTS core.balance_observations AS
SELECT entity_key AS account_key, item_key, run_id, observed_at, currency, balance
FROM core.provider_observations WHERE resource = 'accounts' AND balance IS NOT NULL;

CREATE VIEW IF NOT EXISTS core.bank_transaction_current AS
SELECT * FROM core.provider_current WHERE resource = 'transactions';

CREATE VIEW IF NOT EXISTS core.credit_card_bill_current AS
SELECT * FROM core.provider_current WHERE resource = 'bills';

CREATE VIEW IF NOT EXISTS core.instrument_current AS
SELECT * FROM core.provider_current WHERE resource = 'investments';

CREATE VIEW IF NOT EXISTS core.investment_position_observations AS
SELECT entity_key AS investment_key, item_key, run_id, observed_at,
       economic_date, currency, quantity, unit_value, amount, balance
FROM core.provider_observations WHERE resource = 'investments';

CREATE VIEW IF NOT EXISTS core.investment_movement_current AS
SELECT * FROM core.provider_current WHERE resource = 'investment_movements';
