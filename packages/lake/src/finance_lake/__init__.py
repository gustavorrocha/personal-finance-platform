"""Contract only. Durable Bronze implementation is explicitly deferred to Phase 1."""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import datetime


class ObjectStore(ABC):
    """Keys are relative POSIX paths without PII; hashes are lowercase SHA-256 hex.

    Phase 1 must reject traversal, absolute paths and symlink escapes, fail on
    conflicting writes, fsync before atomic rename, and publish manifests last.
    Deletion must enforce retention and explicit ownership, including backups.
    """

    @abstractmethod
    def put_immutable(self, key: str, payload: bytes) -> str:
        """Return checksum; an identical object is idempotent, a conflict fails."""

    @abstractmethod
    def get(self, key: str) -> bytes:
        """Read an existing object, raising on missing or corrupt data."""

    @abstractmethod
    def list_manifests(self, prefix: str = "") -> Iterator[str]:
        """List committed manifest keys only."""

    @abstractmethod
    def checksum(self, key: str) -> str:
        """Compute SHA-256 from the stored bytes."""

    @abstractmethod
    def verify(self, key: str, expected_sha256: str) -> bool:
        """Verify stored bytes against a trusted manifest."""

    @abstractmethod
    def delete_with_retention_policy(self, key: str, *, not_before: datetime) -> None:
        """Fail closed unless the approved retention policy permits erasure."""


class LocalObjectStore(ObjectStore):
    """Reserved filesystem interface; deliberately abstract and without I/O in Phase 0."""
