import os

import pytest
from cryptography.exceptions import InvalidTag

from scripts.phase0 import decrypt_backup, encrypt_backup, validate_private_path


def test_encrypted_synthetic_backup_roundtrip_and_no_plaintext():
    key = os.urandom(32)
    payload = b"synthetic-only-secret-and-events"
    artifact = encrypt_backup(payload, key)
    assert payload not in artifact
    assert decrypt_backup(artifact, key) == payload
    with pytest.raises(InvalidTag):
        decrypt_backup(artifact, os.urandom(32))
    with pytest.raises(InvalidTag):
        decrypt_backup(artifact[:-1] + bytes([artifact[-1] ^ 1]), key)


def test_private_path_rejects_repo_cloud_and_network_paths(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    for path in (repo, repo / "data", tmp_path / "OneDrive" / "finance"):
        with pytest.raises(ValueError):
            validate_private_path(path, repo)
    with pytest.raises(ValueError):
        validate_private_path("relative-directory", repo)
    assert validate_private_path(tmp_path / "private", repo) == (tmp_path / "private").resolve()
