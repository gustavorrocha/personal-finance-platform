import gzip
import hashlib
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from finance_lake import LocalObjectStore
from finance_lake.bronze import BronzeLake, CorruptionError

FIXTURES = Path(__file__).parent / "fixtures/synthetic"
RUN = UUID("11111111-1111-4111-8111-111111111111")
CAPTURED = datetime(2026, 11, 17, 12, tzinfo=UTC)


@pytest.fixture
def lake(tmp_path):
    return BronzeLake(LocalObjectStore(tmp_path / "lake"))


def capture(lake):
    return lake.commit(
        run_id=RUN,
        retrieved_at=CAPTURED,
        item_alias="synthetic-demo",
        payloads=[
            ("accounts", (FIXTURES / "accounts-response.json").read_bytes()),
            ("transactions", (FIXTURES / "transactions-response.json").read_bytes()),
        ],
    )


def test_same_capture_is_idempotent_and_raw_response_bytes_are_preserved(lake):
    first = capture(lake)
    assert capture(lake) == first
    assert len(list(lake.store.list_manifests())) == 1
    assert len(list(lake.store.root.rglob("*.gz"))) == 2
    info = first.objects[0]
    compressed = lake.store.get(info.object_key)
    assert gzip.decompress(compressed) == (FIXTURES / "accounts-response.json").read_bytes()
    assert hashlib.sha256(compressed).hexdigest() == info.sha256
    assert lake.verify_run(RUN) == first


def test_same_run_with_different_payload_does_not_replace_manifest(lake):
    first = capture(lake)
    with pytest.raises(FileExistsError):
        lake.commit(
            run_id=RUN,
            retrieved_at=CAPTURED,
            item_alias="synthetic-demo",
            payloads=[("accounts", b'{"results":[]}')],
        )
    assert lake.verify_run(RUN) == first


def test_crash_after_objects_before_manifest_recovers_by_retry(lake, monkeypatch):
    put = lake.store.put_immutable

    def crash_on_manifest(key, payload):
        if key.startswith("manifests/"):
            raise SystemExit("simulated process death")
        return put(key, payload)

    monkeypatch.setattr(lake.store, "put_immutable", crash_on_manifest)
    with pytest.raises(SystemExit):
        capture(lake)
    assert list(lake.store.list_manifests()) == []
    assert len(list(lake.store.root.rglob("*.gz"))) == 2
    monkeypatch.setattr(lake.store, "put_immutable", put)
    assert capture(lake) == lake.verify_run(RUN)
    assert len(list(lake.store.root.rglob("*.gz"))) == 2


def test_replay_works_after_manifest_publication_without_metadata_or_network(lake, monkeypatch):
    capture(lake)
    import socket

    def reject_network(*args, **kwargs):
        raise AssertionError("Replay must not open network sockets")

    monkeypatch.setattr(socket, "socket", reject_network)
    reopened = BronzeLake(LocalObjectStore(lake.store.root))
    first = list(reopened.replay(RUN))
    assert len(first) == 3
    assert first == list(reopened.replay(RUN))
    assert len({record.record_id for record in first}) == 3


def test_corruption_is_quarantined_before_any_record_is_replayed(lake):
    manifest = capture(lake)
    broken = lake.store.root / manifest.objects[1].object_key
    broken.write_bytes(b"corrupted synthetic bytes")
    with pytest.raises(CorruptionError):
        next(lake.replay(RUN))
    quarantine = list((lake.store.root / "quarantine").rglob("*.bin"))
    assert len(quarantine) == 1
    assert quarantine[0].read_bytes() == b"corrupted synthetic bytes"
    with pytest.raises(CorruptionError):
        capture(lake)


def test_missing_object_is_quarantined_and_cannot_be_replayed(lake):
    manifest = capture(lake)
    (lake.store.root / manifest.objects[0].object_key).unlink()
    with pytest.raises(CorruptionError):
        list(lake.replay(RUN))
    assert list((lake.store.root / "quarantine").rglob("*.json"))


@pytest.mark.parametrize(
    "payload",
    [b"not-json", b'{"results":NaN}', b'{"results":[1]}', b'{"results":[],"results":[{}]}'],
)
def test_invalid_payload_fails_before_publishing_anything(lake, payload):
    with pytest.raises(ValueError):
        lake.commit(
            run_id=RUN,
            retrieved_at=CAPTURED,
            item_alias="synthetic-demo",
            payloads=[("accounts", payload)],
        )
    assert list(lake.store.list_manifests()) == []
    assert not list(lake.store.root.rglob("*.gz"))


def test_manifest_cannot_inject_paths_or_endpoints(lake):
    manifest = capture(lake)
    data = manifest.model_dump(mode="json")
    data["objects"][0]["object_key"] = "../outside.json"
    import json

    key = lake.manifest_key(manifest)
    (lake.store.root / key).write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CorruptionError):
        list(lake.replay(RUN))


@pytest.mark.parametrize("point", ["before", "after"])
def test_process_death_around_manifest_publication_is_recoverable(lake, point):
    program = """
import os, sys
from finance_lake import LocalObjectStore
from finance_lake.bronze import BronzeLake
from tests.test_bronze import capture
store = LocalObjectStore(sys.argv[1])
put = store.put_immutable
def crash(key, payload):
    if key.startswith('manifests/') and sys.argv[2] == 'before':
        os._exit(77)
    result = put(key, payload)
    if key.startswith('manifests/') and sys.argv[2] == 'after':
        os._exit(77)
    return result
store.put_immutable = crash
capture(BronzeLake(store))
"""
    result = subprocess.run(
        [sys.executable, "-c", program, str(lake.store.root), point],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 77
    assert len(list(lake.store.list_manifests())) == (0 if point == "before" else 1)
    capture(lake)
    assert len(list(lake.replay(RUN))) == 3
