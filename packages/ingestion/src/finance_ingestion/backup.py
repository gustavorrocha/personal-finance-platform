"""Backup archives: the operator's edits as Parquet plus the raw provider captures.

Everything else is derived: Silver comes from replaying the captures and public rates
and prices can be downloaded again. Importing only adds what is missing: captures are
written create-only and replayed, and edit rows the database already has (same
`event_id`, or the same values) are skipped, so importing the same archive twice changes nothing and newer local edits
keep winning.
"""

import hashlib
import io
import json
import os
import re
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from finance_lake import LocalObjectStore
from finance_lake.bronze import BronzeLake

from .agent import JobError

FORMAT = "personal-finance-backup"
VERSION = 1
# Append-only tables holding what the operator decided; each row has an `event_id`.
EDIT_TABLES = (
    "spending_categories",
    "category_rules",
    "spending_rules",
    "spending_reviews",
    "manual_expenses",
    "account_settings",
    "investment_classes",
    "investment_class_assignments",
    "inferred_payment_dismissals",
)
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
NAME = re.compile(r"[a-z_][a-z0-9_]*")
TYPE = re.compile(r"[A-Za-z0-9_(), ']+")

Sql = Callable[..., bytes]


def columns(sql: Sql, table: str) -> list[list[str]]:
    output = sql(
        "SELECT name, type FROM system.columns "
        f"WHERE database = 'core' AND table = '{table}' ORDER BY position FORMAT TSVRaw"
    )
    return [line.split("\t") for line in output.decode().splitlines()]


def count(sql: Sql, table: str) -> int:
    return int(sql(f"SELECT count() FROM core.{table} FORMAT TSV").strip() or 0)


def lake_keys(store: LocalObjectStore) -> list[str]:
    keys = []
    for directory, _, files in os.walk(store.root, followlinks=False):
        for name in files:
            if name == ".finance-lake" or name.endswith(".tmp"):
                continue
            keys.append((Path(directory) / name).relative_to(store.root).as_posix())
    return sorted(keys)


def export_archive(sql: Sql, store: LocalObjectStore) -> bytes:
    manifest = {
        "format": FORMAT,
        "version": VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "tables": {},
        "lake": [],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for table in EDIT_TABLES:
            archive.writestr(
                f"edits/{table}.parquet",
                sql(f"SELECT * FROM core.{table} ORDER BY event_id FORMAT Parquet"),
            )
            manifest["tables"][table] = {
                "columns": columns(sql, table),
                "rows": count(sql, table),
            }
        for key in lake_keys(store):
            payload = store.get(key)
            archive.writestr(f"lake/{key}", payload)
            manifest["lake"].append({"key": key, "sha256": hashlib.sha256(payload).hexdigest()})
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
    return buffer.getvalue()


def read_manifest(archive: zipfile.ZipFile) -> dict:
    if sum(entry.file_size for entry in archive.infolist()) > MAX_ARCHIVE_BYTES:
        raise JobError("Backup archive is too large")
    try:
        manifest = json.loads(archive.read("manifest.json"))
    except (KeyError, ValueError):
        raise JobError("Not a backup made by this platform") from None
    if (
        not isinstance(manifest, dict)
        or manifest.get("format") != FORMAT
        or manifest.get("version") != VERSION
    ):
        raise JobError("Not a backup made by this platform")
    return manifest


def import_archive(sql: Sql, lake: BronzeLake, data: bytes, replay: Callable[[UUID], int]) -> dict:
    if len(data) > MAX_ARCHIVE_BYTES:
        raise JobError("Backup archive is too large")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise JobError("Not a backup made by this platform") from None
    with archive:
        manifest = read_manifest(archive)
        before = set(lake.list_runs())
        objects = 0
        # Objects before manifests, as in a capture, so a run is never visible half written.
        entries = sorted(manifest["lake"], key=lambda e: e["key"].startswith("manifests/"))
        for entry in entries:
            key = entry["key"]
            payload = archive.read(f"lake/{key}")
            if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
                raise JobError("Backup archive integrity check failed")
            try:
                if lake.store.get(key) == payload:
                    continue
            except FileNotFoundError:
                pass
            lake.store.put_immutable(key, payload)
            objects += 1
        runs = [run for run in lake.list_runs() if run not in before]
        records = sum(replay(run) for run in runs)
        edits = 0
        for table, info in manifest["tables"].items():
            spec = info.get("columns") if isinstance(info, dict) else None
            if table not in EDIT_TABLES or not isinstance(spec, list) or not spec:
                raise JobError("Backup archive has an unknown table")
            if any(
                not (isinstance(pair, list) and len(pair) == 2)
                or not NAME.fullmatch(pair[0])
                or not TYPE.fullmatch(pair[1])
                for pair in spec
            ):
                raise JobError("Backup archive has an invalid column")
            names = ", ".join(f"`{name}`" for name, _ in spec)
            # input() takes the structure as a string literal; double its quotes.
            structure = ", ".join(f"`{name}` {kind}" for name, kind in spec).replace("'", "''")
            # A row is already here when its event is, or when every other value matches:
            # seeded defaults get a new event_id per install but share their fixed
            # timestamp, and real edits carry microsecond timestamps, so this never merges
            # two distinct edits.
            values = ", ".join(f"`{name}`" for name, _ in spec if name != "event_id")
            existing = count(sql, table)
            sql(
                f"INSERT INTO core.{table} ({names}) SELECT {names} FROM input('{structure}') "
                f"WHERE event_id NOT IN (SELECT event_id FROM core.{table}) "
                f"AND ({values}) NOT IN (SELECT {values} FROM core.{table}) "
                "SETTINGS transform_null_in = 1 FORMAT Parquet",
                archive.read(f"edits/{table}.parquet"),
            )
            edits += count(sql, table) - existing
    return {"captures": len(runs), "objects": objects, "records": records, "edits": edits}
