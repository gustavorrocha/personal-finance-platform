"""Manifest-last Bronze captures and offline replay. No financial provider access."""

import gzip
import hashlib
import io
import json
import zlib
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid5

from .contracts import ObjectStore
from .manifest import (
    BronzeObject,
    Manifest,
    Resource,
    json_bytes,
    object_identity,
    object_key,
    schema_fingerprint,
)


class CorruptionError(ValueError):
    """A capture cannot be trusted or replayed; payload details are deliberately omitted."""


def _parse(raw: bytes) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("Non-finite JSON value")

    try:
        if len(raw) > 8 * 1024 * 1024:
            raise ValueError("Response exceeds the supported size")
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("results"), list)
            or len(value["results"]) > 10000
            or any(not isinstance(record, dict) for record in value["results"])
        ):
            raise ValueError("Expected an API response with a results object array")
        # Also reject values the replay JSON encoder cannot represent.
        json_bytes(value)
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError("Invalid synthetic API response") from None


def _decompress(payload: bytes) -> bytes:
    with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as stream:
        raw = stream.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError("Compressed response exceeds the supported expanded size")
    return raw


@dataclass(frozen=True)
class ReplayRecord:
    run_id: UUID
    object_id: UUID
    record_id: UUID
    record: dict


class BronzeLake:
    def __init__(self, store: ObjectStore):
        self.store = store

    @staticmethod
    def manifest_key(manifest: Manifest) -> str:
        date = manifest.retrieved_at_utc.date().isoformat()
        return f"manifests/ingestion_date={date}/run_id={manifest.run_id}/manifest.json"

    def commit(
        self,
        *,
        run_id: UUID,
        retrieved_at: datetime,
        item_alias: str,
        payloads: list[tuple[Resource, bytes]],
    ) -> Manifest:
        if not isinstance(run_id, UUID) or not isinstance(retrieved_at, datetime):
            raise ValueError("Capture identity and timestamp must be typed values")
        if self.is_quarantined(run_id):
            raise CorruptionError("Capture is quarantined; automatic resurrection is forbidden")
        try:
            existing_manifest = self.verify_run(run_id)
        except FileNotFoundError:
            existing_manifest = None
        if not 1 <= len(payloads) <= 128 or sum(len(raw) for _, raw in payloads) > 32 * 1024 * 1024:
            raise ValueError("Capture exceeds the supported batch size")
        parts = Counter()
        objects = []
        writes = []
        for resource, raw in payloads:
            if resource not in (
                "accounts",
                "transactions",
                "investments",
                "investment_movements",
                "bills",
            ):
                raise ValueError("Unsupported synthetic resource")
            document = _parse(raw)
            parts[resource] += 1
            part = parts[resource]
            key = object_key(run_id, retrieved_at.date().isoformat(), resource, part)
            try:
                compressed = self.store.get(key)
            except FileNotFoundError:
                buffer = io.BytesIO()
                with gzip.GzipFile(fileobj=buffer, mode="wb", filename="", mtime=0) as stream:
                    stream.write(raw)
                compressed = buffer.getvalue()
            else:
                try:
                    stored_raw = _decompress(compressed)
                except (OSError, EOFError, ValueError, zlib.error):
                    self._quarantine(run_id, key, "invalid-orphan-object")
                    raise CorruptionError("Orphan object integrity validation failed") from None
                if stored_raw != raw:
                    raise FileExistsError("Immutable capture conflict")
            raw_hash = hashlib.sha256(raw).hexdigest()
            objects.append(
                BronzeObject(
                    object_id=object_identity(run_id, resource, part, raw_hash),
                    resource=resource,
                    source_endpoint=f"/{resource}",
                    part_number=part,
                    object_key=key,
                    sha256=hashlib.sha256(compressed).hexdigest(),
                    raw_sha256=raw_hash,
                    size_bytes=len(compressed),
                    raw_size_bytes=len(raw),
                    record_count=len(document["results"]),
                    schema_fingerprint=schema_fingerprint(document),
                )
            )
            writes.append((key, compressed))
        manifest = Manifest(
            run_id=run_id,
            retrieved_at_utc=retrieved_at,
            item_alias=item_alias,
            reference_from=retrieved_at.date(),
            reference_to=retrieved_at.date(),
            objects=tuple(objects),
        )
        key = self.manifest_key(manifest)
        if existing_manifest is not None:
            if existing_manifest.to_bytes() != manifest.to_bytes():
                raise FileExistsError("Immutable capture conflict")
            return existing_manifest
        for object_path, compressed in writes:
            digest = self.store.put_immutable(object_path, compressed)
            if not self.store.verify(object_path, digest):
                raise CorruptionError("Object was not durable before manifest publication")
        self.store.put_immutable(key, manifest.to_bytes())
        return manifest

    def read_manifest(self, run_id: UUID) -> Manifest:
        run_id = UUID(str(run_id))
        keys = [key for key in self.store.list_manifests() if f"/run_id={run_id}/" in key]
        if not keys:
            raise FileNotFoundError("No committed manifest for this run")
        if len(keys) != 1:
            for key in keys:
                self._quarantine(run_id, key, "duplicate-manifest")
            raise CorruptionError("Run identity appears in multiple manifests")
        try:
            encoded = self.store.get(keys[0])
            manifest = Manifest.model_validate_json(encoded)
            if manifest.to_bytes() != encoded:
                raise ValueError("Manifest encoding is not canonical")
            if manifest.run_id != run_id or self.manifest_key(manifest) != keys[0]:
                raise ValueError("Manifest identity does not match its location")
        except (ValueError, OSError):
            self._quarantine(run_id, keys[0], "invalid-manifest")
            raise CorruptionError("Manifest integrity validation failed") from None
        return manifest

    def list_runs(self) -> list[UUID]:
        runs = set()
        for key in self.store.list_manifests():
            try:
                part = key.split("/")[-2]
                run_id = UUID(part.removeprefix("run_id="))
                if part != f"run_id={run_id}":
                    raise ValueError
            except ValueError:
                raise CorruptionError("Invalid manifest location") from None
            runs.add(run_id)
        return sorted(runs)

    def _quarantine(self, run_id: UUID, key: str, reason: str) -> None:
        prefix = f"quarantine/run_id={run_id}"
        self.store.put_immutable(
            f"{prefix}/status.json", json_bytes({"run_id": str(run_id), "status": "quarantined"})
        )
        try:
            payload = self.store.get(key)
        except (OSError, ValueError):
            digest = "unreadable"
        else:
            digest = hashlib.sha256(payload).hexdigest()
            self.store.put_immutable(f"{prefix}/{digest}.bin", payload)
        event = {
            "run_id": str(run_id),
            "object_key": key,
            "reason": reason,
            "observed_sha256": digest,
            "status": "quarantined",
        }
        self.store.put_immutable(
            f"{prefix}/event-{hashlib.sha256(json_bytes(event)).hexdigest()}.json",
            json_bytes(event),
        )

    def _verified_documents(self, manifest: Manifest) -> list[dict]:
        documents = []
        for item in manifest.objects:
            try:
                compressed = self.store.get(item.object_key)
                if (
                    len(compressed) != item.size_bytes
                    or hashlib.sha256(compressed).hexdigest() != item.sha256
                ):
                    raise ValueError("Object checksum mismatch")
                raw = _decompress(compressed)
                document = _parse(raw)
                if (
                    len(raw) != item.raw_size_bytes
                    or hashlib.sha256(raw).hexdigest() != item.raw_sha256
                    or len(document["results"]) != item.record_count
                    or schema_fingerprint(document) != item.schema_fingerprint
                ):
                    raise ValueError("Object provenance mismatch")
            except (OSError, ValueError, EOFError, zlib.error):
                self._quarantine(manifest.run_id, item.object_key, "invalid-object")
                raise CorruptionError("Capture quarantined after integrity failure") from None
            documents.append(document)
        return documents

    def verify_run(self, run_id: UUID) -> Manifest:
        manifest = self.read_manifest(run_id)
        if self.is_quarantined(run_id):
            raise CorruptionError("Capture is quarantined; automatic resurrection is forbidden")
        self._verified_documents(manifest)
        return manifest

    def is_quarantined(self, run_id: UUID) -> bool:
        try:
            self.store.get(f"quarantine/run_id={UUID(str(run_id))}/status.json")
        except FileNotFoundError:
            return False
        return True

    def replay(self, run_id: UUID) -> Iterator[ReplayRecord]:
        manifest = self.read_manifest(run_id)
        if self.is_quarantined(run_id):
            raise CorruptionError("Capture is quarantined; automatic resurrection is forbidden")
        documents = self._verified_documents(manifest)
        # Verify the entire capture before yielding any record to a warehouse writer.
        for item, document in zip(manifest.objects, documents, strict=True):
            for index, record in enumerate(document["results"]):
                yield ReplayRecord(
                    manifest.run_id, item.object_id, uuid5(item.object_id, str(index)), record
                )
