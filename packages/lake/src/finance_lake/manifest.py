"""Closed, versioned provenance contracts for synthetic captures."""

import hashlib
import json
from datetime import date, timedelta
from typing import Annotated, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Resource = Literal["accounts", "transactions", "investments", "investment_movements", "bills"]
SHA256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


def object_key(run_id: UUID, date: str, resource: str, part: int) -> str:
    return (
        f"bronze/source=synthetic/resource={resource}/ingestion_date={date}/"
        f"run_id={run_id}/part-{part:04}.json.gz"
    )


def object_identity(run_id: UUID, resource: str, part: int, raw_sha256: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"finance:{run_id}:{resource}:{part}:{raw_sha256}")


def json_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


class BronzeObject(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    object_id: UUID
    resource: Resource
    source_endpoint: str
    part_number: int = Field(ge=1, le=128)
    object_key: str
    sha256: SHA256
    raw_sha256: SHA256
    size_bytes: int = Field(gt=0, le=16 * 1024 * 1024)
    raw_size_bytes: int = Field(gt=0, le=8 * 1024 * 1024)
    record_count: int = Field(ge=0, le=10000)
    schema_fingerprint: SHA256
    previous_object_ids: tuple[UUID, ...] = ()


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest_version: Literal[1] = 1
    run_id: UUID
    source: Literal["synthetic"] = "synthetic"
    item_alias: str = Field(pattern=r"^synthetic-[a-z][a-z0-9-]{0,23}$")
    retrieved_at_utc: AwareDatetime
    reference_from: date
    reference_to: date
    collector_version: Literal["0.1.0"] = "0.1.0"
    consent_state: Literal["synthetic"] = "synthetic"
    status: Literal["complete"] = "complete"
    objects: tuple[BronzeObject, ...] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_capture(self):
        if self.retrieved_at_utc.utcoffset() != timedelta(0):
            raise ValueError("Capture timestamp must use UTC")
        if self.reference_from > self.reference_to:
            raise ValueError("Reference interval must be ordered")
        keys = set()
        total = 0
        for item in self.objects:
            expected = object_key(
                self.run_id,
                self.retrieved_at_utc.date().isoformat(),
                item.resource,
                item.part_number,
            )
            identity = object_identity(
                self.run_id, item.resource, item.part_number, item.raw_sha256
            )
            if item.object_key != expected or item.object_id != identity or expected in keys:
                raise ValueError("Invalid object identity or layout")
            if item.source_endpoint != f"/{item.resource}":
                raise ValueError("Endpoint must not contain identifiers or query strings")
            keys.add(expected)
            total += item.raw_size_bytes
        if total > 32 * 1024 * 1024:
            raise ValueError("Capture exceeds the supported batch size")
        return self

    def to_bytes(self) -> bytes:
        return json_bytes(self.model_dump(mode="json"))


def schema_fingerprint(value: object) -> str:
    def shape(item):
        if isinstance(item, dict):
            return {key: shape(child) for key, child in sorted(item.items())}
        if isinstance(item, list):
            return sorted({json_bytes(shape(child)).decode() for child in item})
        return type(item).__name__

    return hashlib.sha256(json_bytes(shape(value))).hexdigest()
