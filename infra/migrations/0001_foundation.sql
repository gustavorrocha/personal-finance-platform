CREATE DATABASE IF NOT EXISTS core;
CREATE DATABASE IF NOT EXISTS analytics;
CREATE DATABASE IF NOT EXISTS metadata;

CREATE TABLE IF NOT EXISTS metadata.schema_migrations
(
    version String,
    sha256 FixedString(64),
    applied_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = MergeTree ORDER BY version;

-- Synthetic infrastructure probe only; not a financial domain table.
CREATE TABLE IF NOT EXISTS metadata.synthetic_events
(
    event_id UInt64,
    amount Decimal(18, 2),
    label String
)
ENGINE = MergeTree ORDER BY event_id;
