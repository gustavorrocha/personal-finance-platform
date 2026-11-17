import inspect

import pytest
from finance_lake import LocalObjectStore, ObjectStore


def test_local_store_is_only_an_interface():
    assert issubclass(LocalObjectStore, ObjectStore)
    assert inspect.isabstract(LocalObjectStore)
    with pytest.raises(TypeError):
        LocalObjectStore()
    assert LocalObjectStore.__abstractmethods__ == {
        "put_immutable",
        "get",
        "list_manifests",
        "checksum",
        "verify",
        "delete_with_retention_policy",
    }
