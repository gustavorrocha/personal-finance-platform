import inspect

import pytest
from finance_lake import LocalObjectStore, ObjectStore


def test_storage_interface_remains_abstract_but_local_backend_is_concrete(tmp_path):
    assert issubclass(LocalObjectStore, ObjectStore)
    assert inspect.isabstract(ObjectStore)
    assert not inspect.isabstract(LocalObjectStore)
    with pytest.raises(TypeError):
        ObjectStore()
    assert ObjectStore.__abstractmethods__ == {
        "put_immutable",
        "get",
        "list_manifests",
        "checksum",
        "verify",
        "delete_with_retention_policy",
    }
    store = LocalObjectStore(tmp_path / "lake")
    assert store.put_immutable("bronze/example.json.gz", b"synthetic")
    assert store.get("bronze/example.json.gz") == b"synthetic"
