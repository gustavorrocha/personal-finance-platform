import io
import json
import zipfile
from uuid import uuid4

import pytest
from finance_ingestion.agent import JobError
from finance_ingestion.backup import EDIT_TABLES, FORMAT, VERSION, export_archive, import_archive
from finance_ingestion.collection import collect
from finance_ingestion.silver import SilverWarehouse
from finance_ingestion.warehouse import BronzeWarehouse
from finance_lake import LocalObjectStore
from finance_lake.bronze import BronzeLake

from tests.test_provider_ingestion import ITEM, WHEN
from tests.test_provider_ingestion import isolated_warehouse as isolated_warehouse
from tests.test_provider_ingestion import pipeline as pipeline


def archive(manifest: dict | None, extra: dict[str, bytes] | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as stream:
        if manifest is not None:
            stream.writestr("manifest.json", json.dumps(manifest))
        for name, payload in (extra or {}).items():
            stream.writestr(name, payload)
    return buffer.getvalue()


def refuse(query, native=b""):
    pytest.fail("An invalid archive must be refused before touching ClickHouse")


@pytest.mark.parametrize(
    "data",
    [
        b"not a zip",
        archive(None),
        archive({"format": "other", "version": VERSION, "tables": {}, "lake": []}),
        archive({"format": FORMAT, "version": VERSION + 1, "tables": {}, "lake": []}),
    ],
)
def test_foreign_archives_are_refused(tmp_path, data):
    lake = BronzeLake(LocalObjectStore(tmp_path / "lake"))
    with pytest.raises(JobError):
        import_archive(refuse, lake, data, replay=lambda run: 0)


def test_tampered_captures_and_unknown_tables_are_refused(tmp_path):
    lake = BronzeLake(LocalObjectStore(tmp_path / "lake"))
    tampered = {
        "format": FORMAT,
        "version": VERSION,
        "tables": {},
        "lake": [{"key": "bronze/x.json", "sha256": "0" * 64}],
    }
    with pytest.raises(JobError, match="integrity"):
        import_archive(refuse, lake, archive(tampered, {"lake/bronze/x.json": b"{}"}), len)
    unknown = {
        "format": FORMAT,
        "version": VERSION,
        "tables": {"users": {"columns": [["event_id", "UUID"]]}},
        "lake": [],
    }
    with pytest.raises(JobError, match="unknown table"):
        import_archive(lambda query, native=b"": b"0", lake, archive(unknown), len)
    assert not list(lake.store.root.rglob("x.json"))


def test_backup_round_trip_restores_captures_and_edits_once(pipeline, isolated_warehouse, tmp_path):
    _, lake, client = pipeline
    source = isolated_warehouse()
    run = uuid4()
    collect(client, lake, ITEM, run, WHEN, None)
    source.replay(run)
    # One row per table; two tables constrain a column to known values.
    valid = {"category_rules": ", scope", "spending_reviews": ", decision"}
    value = {"category_rules": ", 'merchant'", "spending_reviews": ", 'include'"}
    for table in EDIT_TABLES:
        source.execute(
            f"INSERT INTO core.{table} (event_id{valid.get(table, '')}) "
            f"SELECT generateUUIDv4(){value.get(table, '')}"
        )

    data = export_archive(source.execute, lake.store)

    target_sql = isolated_warehouse().execute
    target_lake = BronzeLake(LocalObjectStore(tmp_path / "restored"))
    target = SilverWarehouse(BronzeWarehouse(target_lake, target_sql), target_sql)
    first = import_archive(target_sql, target_lake, data, target.replay)
    assert first["captures"] == 1
    assert first["edits"] == len(EDIT_TABLES)
    again = import_archive(target_sql, target_lake, data, target.replay)
    assert again == {"captures": 0, "objects": 0, "records": 0, "edits": 0}

    query = "SELECT count() FROM core.provider_current FORMAT TSV"
    assert target_sql(query) == source.execute(query)
