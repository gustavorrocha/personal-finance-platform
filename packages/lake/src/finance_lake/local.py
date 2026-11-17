"""Private filesystem storage with atomic, no-overwrite publication."""

import hashlib
import os
import re
import tempfile
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from .contracts import ObjectStore

MAX_OBJECT_BYTES = 16 * 1024 * 1024
MARKER = b"personal-finance-lake-v1\n"
SEGMENT = re.compile(r"[a-z0-9][a-z0-9._=-]{0,127}\Z")
RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def _no_links(path: Path) -> None:
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError("Linked storage paths are forbidden")


def _publish(temporary: Path, destination: Path) -> None:
    if os.name == "nt":
        os.rename(temporary, destination)  # Windows rename refuses an existing destination.
    else:
        os.link(temporary, destination, follow_symlinks=False)


class LocalObjectStore(ObjectStore):
    def __init__(self, root: Path):
        root = Path(root)
        if not root.is_absolute() or str(root).startswith(("\\\\", "//")):
            raise ValueError("Storage requires an absolute local path")
        _no_links(root)
        if any((parent / ".git").exists() for parent in (root, *root.parents)):
            raise ValueError("Storage inside a Git repository is forbidden")
        if any(
            word in str(root).lower()
            for word in ("onedrive", "dropbox", "google drive", "googledrive", "icloud")
        ):
            raise ValueError("Cloud-synchronized storage is forbidden")
        self.root = root.resolve()
        for name in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
            if os.environ.get(name) and self.root.is_relative_to(Path(os.environ[name]).resolve()):
                raise ValueError("Cloud-synchronized storage is forbidden")
        try:
            self.root.mkdir(mode=0o700)
        except FileExistsError:
            pass
        else:
            marker = self.root / ".finance-lake"
            with marker.open("xb") as stream:
                stream.write(MARKER)
                stream.flush()
                os.fsync(stream.fileno())
            marker.chmod(0o600)
        self._owned()

    def _owned(self) -> None:
        _no_links(self.root)
        marker = self.root / ".finance-lake"
        _no_links(marker)
        if not marker.is_file() or marker.read_bytes() != MARKER:
            raise PermissionError("Storage ownership could not be verified")
        if os.name == "posix" and self.root.stat().st_mode & 0o077:
            raise PermissionError("Storage directory permissions must be private")

    def _path(self, key: str) -> Path:
        self._owned()
        if not isinstance(key, str) or len(key) > 512:
            raise ValueError("Invalid object key")
        parts = key.split("/")
        if any(
            not SEGMENT.fullmatch(part) or part.endswith(".") or part.split(".")[0] in RESERVED
            for part in parts
        ):
            raise ValueError("Invalid object key")
        path = self.root.joinpath(*parts)
        _no_links(path)
        if not path.resolve().is_relative_to(self.root):
            raise ValueError("Object escaped storage root")
        return path

    def _sync_parents(self, directory: Path) -> None:
        # Windows exposes file fsync, but not portable directory fsync; validate power-loss on NTFS.
        if os.name != "posix":
            return
        while directory.is_relative_to(self.root):
            descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            if directory == self.root:
                break
            directory = directory.parent

    def put_immutable(self, key: str, payload: bytes) -> str:
        path = self._path(key)
        if not isinstance(payload, bytes) or len(payload) > MAX_OBJECT_BYTES:
            raise ValueError("Object exceeds the supported size or type")
        digest = hashlib.sha256(payload).hexdigest()
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._path(key)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=path.parent, suffix=".tmp", delete=False
            ) as stream:
                temporary = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != digest:
                raise OSError("Staged object integrity check failed")
            try:
                _publish(temporary, path)
            except FileExistsError:
                if self.get(key) != payload:
                    raise FileExistsError("Immutable object conflict") from None
            self._sync_parents(path.parent)
        finally:
            if temporary is not None:
                # Only remove the temporary file allocated by this invocation, never a derived tree.
                temporary.unlink(missing_ok=True)
        return digest

    def get(self, key: str) -> bytes:
        path = self._path(key)
        with path.open("rb") as stream:
            payload = stream.read(MAX_OBJECT_BYTES + 1)
        if len(payload) > MAX_OBJECT_BYTES:
            raise ValueError("Stored object exceeds the supported size")
        return payload

    def checksum(self, key: str) -> str:
        return hashlib.sha256(self.get(key)).hexdigest()

    def verify(self, key: str, expected_sha256: str) -> bool:
        if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
            raise ValueError("Invalid SHA-256")
        try:
            return self.checksum(key) == expected_sha256
        except FileNotFoundError:
            return False

    def list_manifests(self, prefix: str = "") -> Iterator[str]:
        start = self._path(prefix) if prefix else self._path("manifests")
        if not start.is_relative_to(self.root / "manifests"):
            raise ValueError("Manifest listing requires the manifests prefix")
        if not start.exists():
            return
        for directory, folders, files in os.walk(start, followlinks=False):
            for name in folders:
                _no_links(Path(directory) / name)
            if "manifest.json" in files:
                key = (Path(directory) / "manifest.json").relative_to(self.root).as_posix()
                self._path(key)
                yield key

    def delete_with_retention_policy(self, key: str, *, not_before: datetime) -> None:
        self._path(key)
        # shortcut: erasure is disabled until an approved policy also covers referenced backups.
        raise PermissionError("Deletion requires an approved retention and backup erasure policy")
