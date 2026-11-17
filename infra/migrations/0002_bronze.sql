CREATE TABLE IF NOT EXISTS metadata.bronze_objects
(
    run_id UUID,
    object_id UUID,
    resource LowCardinality(String),
    object_key String,
    manifest_key String,
    sha256 FixedString(64),
    manifest_sha256 FixedString(64),
    size_bytes UInt64,
    record_count UInt64,
    retrieved_at_utc DateTime64(3, 'UTC'),
    status LowCardinality(String),
    status_version UInt8,
    indexed_at_utc DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(status_version)
ORDER BY (run_id, object_id);

-- Repeated inserts are logically idempotent before background merges.
-- Quarantine version 2 permanently outranks complete version 1.
CREATE VIEW IF NOT EXISTS metadata.bronze_objects_current AS
SELECT * FROM metadata.bronze_objects FINAL;

-- Synthetic replay evidence only; real Silver/Gold models belong to later phases.
CREATE TABLE IF NOT EXISTS metadata.synthetic_bronze_records
(
    run_id UUID,
    object_id UUID,
    record_id UUID,
    record_json String
)
ENGINE = ReplacingMergeTree
ORDER BY (run_id, object_id, record_id);

CREATE VIEW IF NOT EXISTS metadata.synthetic_bronze_records_current AS
SELECT * FROM metadata.synthetic_bronze_records FINAL;
