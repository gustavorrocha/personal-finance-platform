"""Validate synthetic Bronze recovery against local and independent ClickHouse instances."""

import hashlib
import os
import time
from uuid import uuid4

from finance_ingestion.synthetic import SYNTHETIC_RUN, capture_synthetic
from finance_ingestion.warehouse import BronzeWarehouse
from finance_lake import LocalObjectStore
from finance_lake.bronze import BronzeLake, CorruptionError

from scripts.phase0 import COMPOSE, ROOT, command, sql, validate_private_path


def fingerprint(execute) -> bytes:
    return execute(
        "SELECT run_id, object_id, record_id, record_json "
        "FROM metadata.synthetic_bronze_records_published ORDER BY record_id "
        "FORMAT JSONEachRow"
    )


def main() -> None:
    private = validate_private_path(os.environ["FINANCE_PRIVATE_DIR"])
    lake = BronzeLake(LocalObjectStore(private / "lake"))
    fixtures = ROOT / "tests/fixtures/synthetic"
    first = capture_synthetic(lake, fixtures)
    assert capture_synthetic(lake, fixtures) == first
    warehouse = BronzeWarehouse(lake, sql)
    assert warehouse.index_run(SYNTHETIC_RUN) == 2
    assert warehouse.replay(SYNTHETIC_RUN) == 3
    assert warehouse.replay(SYNTHETIC_RUN) == 3
    assert sql("SELECT count() FROM metadata.bronze_objects_current").strip() == b"2"
    assert warehouse.rebuild() == 3
    before = fingerprint(sql)
    assert warehouse.rebuild() == 3
    assert fingerprint(sql) == before

    name = "finance-bronze-recovery-" + uuid4().hex
    command(COMPOSE + ["run", "--rm", "--no-deps", "-d", "--name", name, "restore"])
    try:

        def isolated(query, native=b""):
            return sql(query, container=name, native=native)

        for _ in range(60):
            try:
                isolated("SELECT 1")
                break
            except RuntimeError:
                time.sleep(1)
        else:
            raise RuntimeError("Recovery instance did not become ready")
        for migration in sorted((ROOT / "infra/migrations").glob("*.sql")):
            isolated(migration.read_text())
        restored = BronzeWarehouse(lake, isolated)
        assert restored.rebuild() == 3
        assert fingerprint(isolated) == before

        damaged = BronzeLake(LocalObjectStore(private / f"lake-quarantine-test-{uuid4().hex}"))
        manifest = capture_synthetic(damaged, fixtures)
        (damaged.store.root / manifest.objects[0].object_key).write_bytes(b"synthetic-corruption")
        try:
            BronzeWarehouse(damaged, isolated).rebuild()
        except CorruptionError:
            pass
        else:
            raise AssertionError("Corruption was not detected")
        assert fingerprint(isolated) == before
        assert (
            isolated(
                "SELECT count() FROM metadata.bronze_objects_current WHERE status='quarantined'"
            ).strip()
            == b"2"
        )
    finally:
        command(["docker", "rm", "-f", name])
    print(
        "Bronze validation passed: idempotency, offline rebuild, clean-instance recovery, "
        "quarantine and unchanged published data."
    )
    print("Synthetic replay SHA-256:", hashlib.sha256(before).hexdigest())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Bronze validation failed; sensitive details suppressed.") from None
