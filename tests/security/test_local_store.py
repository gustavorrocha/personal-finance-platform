import hashlib
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest
from finance_lake import LocalObjectStore


@pytest.fixture
def store(tmp_path):
    return LocalObjectStore(tmp_path / "lake")


def test_immutable_writes_are_idempotent_and_conflicts_do_not_replace_data(store):
    payload = b'{"synthetic": true}'
    key = "bronze/source=synthetic/part-0001.json.gz"
    expected = hashlib.sha256(payload).hexdigest()
    assert store.put_immutable(key, payload) == expected
    assert store.put_immutable(key, payload) == expected
    with pytest.raises(FileExistsError):
        store.put_immutable(key, b"different")
    assert store.get(key) == payload
    assert store.verify(key, expected)


@pytest.mark.skipif(os.name != "nt", reason="Windows extended-length path spelling")
def test_resolved_windows_path_can_have_an_extended_prefix(store, monkeypatch):
    original = Path.resolve

    def resolve(path, *args, **kwargs):
        resolved = original(path, *args, **kwargs)
        return Path("\\\\?\\" + str(resolved)) if path.name == "race.json" else resolved

    monkeypatch.setattr(Path, "resolve", resolve)
    store.put_immutable("bronze/race.json", b"unchanged")
    assert store.get("bronze/race.json") == b"unchanged"
    assert not list(store.root.rglob("*.tmp"))


@pytest.mark.parametrize(
    "key",
    [
        "",
        "../escape",
        "/absolute",
        "C:/escape",
        "bronze/../escape",
        "bronze//x",
        "bronze/./x",
        r"bronze\escape",
        "bronze/a:stream",
        "bronze/trailing.",
        "bronze/CON",
        "bronze/secrets?token=bad",
        "bronze/name with spaces",
    ],
)
def test_unsafe_keys_are_rejected(store, key):
    with pytest.raises(ValueError):
        store.put_immutable(key, b"never written")


def test_existing_directory_without_ownership_marker_is_not_adopted(tmp_path):
    existing = tmp_path / "unowned"
    existing.mkdir()
    with pytest.raises(PermissionError):
        LocalObjectStore(existing)
    assert not list(existing.iterdir())


def test_root_cannot_be_in_a_repository_or_cloud_sync_folder(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    for root in (repo / "lake", tmp_path / "OneDrive" / "lake"):
        with pytest.raises(ValueError):
            LocalObjectStore(root)


def test_symlink_or_windows_junction_escape_is_rejected(store, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    if os.name == "nt":
        subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(store.root / "escape"), str(outside)],
            check=True,
            capture_output=True,
        )
    else:
        (store.root / "escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        store.put_immutable("escape/stolen.json", b"synthetic")
    assert not list(outside.iterdir())


def test_simultaneous_conflicting_writes_publish_one_complete_payload(store):
    def write(payload):
        try:
            store.put_immutable("bronze/race.json", payload)
            return payload
        except FileExistsError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, [b"a" * 4096, b"b" * 4096]))
    assert sum(result is not None for result in results) == 1
    assert store.get("bronze/race.json") in results


def test_failed_publication_does_not_leave_a_partial_final_object(store, monkeypatch):
    from finance_lake import local

    def fail(*args):
        raise OSError("simulated interruption")

    monkeypatch.setattr(local, "_publish", fail)
    with pytest.raises(OSError):
        store.put_immutable("bronze/interrupted.json", b"synthetic")
    assert not (store.root / "bronze/interrupted.json").exists()
    assert list(store.list_manifests()) == []


def test_manifest_listing_ignores_temporary_and_uncommitted_objects(store):
    store.put_immutable("bronze/orphan.json", b"{}")
    store.put_immutable("manifests/run-a/manifest.json.tmp", b"partial")
    store.put_immutable("manifests/run-b/manifest.json", b"{}")
    assert list(store.list_manifests()) == ["manifests/run-b/manifest.json"]


def test_deletion_fails_closed_without_an_approved_backup_retention_policy(store):
    store.put_immutable("bronze/retained.json", b"{}")
    with pytest.raises(PermissionError):
        store.delete_with_retention_policy("bronze/retained.json", not_before=datetime.now(UTC))
    assert store.get("bronze/retained.json") == b"{}"
