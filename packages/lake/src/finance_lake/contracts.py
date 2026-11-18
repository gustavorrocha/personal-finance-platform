"""Storage boundary shared by local and future object-store backends."""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import datetime


class ObjectStore(ABC):
    """Relative POSIX keys without PII; lowercase SHA-256 hashes; no overwrites."""

    @abstractmethod
    def put_immutable(self, key: str, payload: bytes) -> str:
        """Return checksum; identical bytes are idempotent and conflicts fail."""

    @abstractmethod
    def get(self, key: str) -> bytes:
        """Read stored bytes; callers must verify against a trusted manifest."""

    @abstractmethod
    def list_manifests(self, prefix: str = "") -> Iterator[str]:
        """List atomically published manifest keys only."""

    @abstractmethod
    def checksum(self, key: str) -> str:
        """Compute SHA-256 from stored bytes."""

    @abstractmethod
    def verify(self, key: str, expected_sha256: str) -> bool:
        """Verify stored bytes against a trusted manifest."""

    @abstractmethod
    def delete_with_retention_policy(self, key: str, *, not_before: datetime) -> None:
        """Fail closed unless retention and backup erasure policies authorize deletion."""
