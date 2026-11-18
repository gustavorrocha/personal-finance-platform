-- Windows bind mounts may not support renameat2 / EXCHANGE TABLES.
-- Stage complete generations as rows, then publish one pointer event last.
CREATE TABLE IF NOT EXISTS metadata.synthetic_bronze_record_versions
(
    build_id UUID,
    run_id UUID,
    object_id UUID,
    record_id UUID,
    record_json String
)
ENGINE = ReplacingMergeTree
ORDER BY (build_id, run_id, object_id, record_id);

CREATE TABLE IF NOT EXISTS metadata.synthetic_bronze_publications
(
    build_id UUID,
    version UInt64,
    publication_id UUID
)
ENGINE = MergeTree
ORDER BY (version, publication_id);

-- Preserve synthetic rows already written before this additive migration.
INSERT INTO metadata.synthetic_bronze_record_versions
SELECT toUUID('00000000-0000-0000-0000-000000000000'), run_id, object_id, record_id, record_json
FROM metadata.synthetic_bronze_records FINAL;

INSERT INTO metadata.synthetic_bronze_publications
SELECT toUUID('00000000-0000-0000-0000-000000000000'), 0,
       toUUID('00000000-0000-0000-0000-000000000000')
WHERE NOT EXISTS (SELECT 1 FROM metadata.synthetic_bronze_publications);

CREATE VIEW IF NOT EXISTS metadata.synthetic_bronze_records_published AS
SELECT run_id, object_id, record_id, record_json
FROM metadata.synthetic_bronze_record_versions FINAL
WHERE build_id = (
    SELECT argMax(build_id, (version, publication_id))
    FROM metadata.synthetic_bronze_publications
);
