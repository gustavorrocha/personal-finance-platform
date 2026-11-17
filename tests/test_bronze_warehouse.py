import json
from pathlib import Path
from uuid import uuid4

import pytest
from finance_ingestion.warehouse import BronzeWarehouse
from finance_lake import LocalObjectStore
from finance_lake.bronze import BronzeLake, CorruptionError

from tests.test_bronze import capture


def test_index_is_recoverable_from_manifest_when_the_first_database_write_fails(tmp_path):
    lake = BronzeLake(LocalObjectStore(tmp_path / "lake"))
    manifest = capture(lake)

    def fail(query, native=b""):
        raise RuntimeError("simulated local database outage")

    with pytest.raises(RuntimeError):
        BronzeWarehouse(lake, fail).index_run(manifest.run_id)
    assert lake.verify_run(manifest.run_id) == manifest
    inserts = []
    warehouse = BronzeWarehouse(lake, lambda query, native=b"": inserts.append((query, native)))
    assert warehouse.index_run(manifest.run_id) == 2
    indexed = [json.loads(line) for line in inserts[0][1].splitlines()]
    assert all(row["status"] == "complete" and row["status_version"] == 1 for row in indexed)
    assert len({row["object_id"] for row in indexed}) == 2


def test_rebuild_uses_deterministic_records_and_a_publish_after_validation(tmp_path):
    lake = BronzeLake(LocalObjectStore(tmp_path / "lake"))
    capture(lake)
    queries = []
    warehouse = BronzeWarehouse(lake, lambda query, native=b"": queries.append((query, native)))
    assert warehouse.rebuild() == 3
    first = next(
        payload
        for query, payload in queries
        if "INSERT INTO metadata.synthetic_bronze_record_versions" in query
    )
    assert "INSERT INTO metadata.synthetic_bronze_publications" in queries[-1][0]
    queries.clear()
    assert warehouse.rebuild() == 3
    second = next(
        payload
        for query, payload in queries
        if "INSERT INTO metadata.synthetic_bronze_record_versions" in query
    )

    def without_build(payload):
        return [
            {key: value for key, value in json.loads(line).items() if key != "build_id"}
            for line in payload.splitlines()
        ]

    assert without_build(first) == without_build(second)


def test_corrupt_capture_is_indexed_as_quarantined_and_never_published(tmp_path):
    lake = BronzeLake(LocalObjectStore(tmp_path / "lake"))
    manifest = capture(lake)
    (lake.store.root / manifest.objects[0].object_key).write_bytes(b"broken")
    queries = []
    warehouse = BronzeWarehouse(lake, lambda query, native=b"": queries.append((query, native)))
    with pytest.raises(CorruptionError):
        warehouse.rebuild()
    assert not any(
        "INSERT INTO metadata.synthetic_bronze_publications" in query for query, _ in queries
    )
    records = [
        json.loads(line)
        for query, payload in queries
        if "INSERT INTO metadata.bronze_objects" in query
        for line in payload.splitlines()
    ]
    assert records and all(row["status_version"] == 2 for row in records)


def test_migration_adds_exact_current_views_without_a_second_database():
    sql = Path("infra/migrations/0002_bronze.sql").read_text()
    assert "ReplacingMergeTree(status_version)" in sql
    assert "FROM metadata.bronze_objects FINAL" in sql
    assert "FROM metadata.synthetic_bronze_records FINAL" in sql
    assert "CREATE DATABASE" not in sql


def test_rebuild_rejects_manifest_copied_under_a_different_run_id(tmp_path):
    lake = BronzeLake(LocalObjectStore(tmp_path / "lake"))
    manifest = capture(lake)
    wrong_run = uuid4()
    key = lake.manifest_key(manifest).replace(str(manifest.run_id), str(wrong_run))
    lake.store.put_immutable(key, manifest.to_bytes())
    queries = []
    warehouse = BronzeWarehouse(lake, lambda query, native=b"": queries.append(query))
    with pytest.raises(CorruptionError):
        warehouse.rebuild()
    assert lake.is_quarantined(wrong_run)
    assert not any("INSERT INTO metadata.synthetic_bronze_publications" in q for q in queries)
