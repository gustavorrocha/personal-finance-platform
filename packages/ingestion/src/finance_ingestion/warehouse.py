"""Reconstructible ClickHouse indexes and synthetic replay evidence."""

import hashlib
from collections.abc import Callable
from uuid import UUID, uuid4

from finance_lake.bronze import BronzeLake, CorruptionError, ReplayRecord
from finance_lake.manifest import json_bytes

Execute = Callable[..., bytes]


class BronzeWarehouse:
    def __init__(self, lake: BronzeLake, execute: Execute):
        self.lake = lake
        self.execute = execute

    def index_run(self, run_id: UUID) -> int:
        run_id = UUID(str(run_id))
        try:
            manifest = self.lake.read_manifest(run_id)
        except CorruptionError:
            self.execute(
                "INSERT INTO metadata.bronze_objects "
                "(run_id,object_id,resource,object_key,manifest_key,sha256,manifest_sha256,"
                "size_bytes,record_count,retrieved_at_utc,status,status_version) "
                "SELECT run_id,object_id,resource,object_key,manifest_key,sha256,manifest_sha256,"
                "size_bytes,record_count,retrieved_at_utc,'quarantined',2 "
                f"FROM metadata.bronze_objects_current WHERE run_id='{run_id}'"
            )
            raise
        failed = False
        try:
            self.lake.verify_run(run_id)
        except CorruptionError:
            failed = True
        rows = []
        manifest_hash = hashlib.sha256(manifest.to_bytes()).hexdigest()
        for item in manifest.objects:
            rows.append(
                {
                    "run_id": str(manifest.run_id),
                    "object_id": str(item.object_id),
                    "resource": item.resource,
                    "object_key": item.object_key,
                    "manifest_key": self.lake.manifest_key(manifest),
                    "sha256": item.sha256,
                    "manifest_sha256": manifest_hash,
                    "size_bytes": item.size_bytes,
                    "record_count": item.record_count,
                    "retrieved_at_utc": manifest.retrieved_at_utc.strftime("%Y-%m-%d %H:%M:%S.%f")[
                        :-3
                    ],
                    "status": "quarantined" if failed else "complete",
                    "status_version": 2 if failed else 1,
                }
            )
        self.execute(
            "INSERT INTO metadata.bronze_objects FORMAT JSONEachRow",
            native=b"\n".join(json_bytes(row) for row in rows) + b"\n",
        )
        if failed:
            raise CorruptionError("Quarantined capture indexed; replay refused")
        return len(rows)

    def _records(self, run_id: UUID) -> list[ReplayRecord]:
        self.index_run(run_id)
        try:
            return list(self.lake.replay(run_id))
        except CorruptionError:
            self.index_run(run_id)
            raise

    @staticmethod
    def _encode(records: list[ReplayRecord], build_id: UUID) -> bytes:
        rows = [
            {
                "build_id": str(build_id),
                "run_id": str(item.run_id),
                "object_id": str(item.object_id),
                "record_id": str(item.record_id),
                "record_json": json_bytes(item.record).decode(),
            }
            for item in records
        ]
        return b"\n".join(json_bytes(row) for row in rows) + (b"\n" if rows else b"")

    def _append(self, records: list[ReplayRecord], build_id: UUID) -> None:
        if records:
            self.execute(
                "INSERT INTO metadata.synthetic_bronze_record_versions FORMAT JSONEachRow",
                native=self._encode(records, build_id),
            )

    def _publish(self, build_id: UUID) -> None:
        # Single-writer operations; the final append makes a complete generation visible.
        self.execute(
            "INSERT INTO metadata.synthetic_bronze_publications "
            f"SELECT toUUID('{build_id}'), max(version)+1, generateUUIDv4() "
            "FROM metadata.synthetic_bronze_publications"
        )

    def replay(self, run_id: UUID) -> int:
        run_id = UUID(str(run_id))
        records = self._records(run_id)
        build_id = uuid4()
        self.execute(
            "INSERT INTO metadata.synthetic_bronze_record_versions "
            f"SELECT toUUID('{build_id}'), run_id, object_id, record_id, record_json "
            "FROM metadata.synthetic_bronze_records_published "
            f"WHERE run_id != toUUID('{run_id}')"
        )
        self._append(records, build_id)
        self._publish(build_id)
        return len(records)

    def rebuild(self) -> int:
        runs = self.lake.list_runs()
        if not runs:
            raise FileNotFoundError("Rebuild requires at least one committed capture")
        build_id = uuid4()
        count = 0
        for run_id in runs:
            records = self._records(run_id)
            self._append(records, build_id)
            count += len(records)
        self._publish(build_id)
        return count
