"""Closed, versioned provenance contracts for Bronze captures."""

import hashlib
import json
import re
from datetime import date, timedelta
from typing import Annotated, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Resource = Literal[
    "accounts",
    "transactions",
    "investments",
    "investment_movements",
    "bills",
    "items",
    "resources",
    "transaction_deletions",
]
Source = Literal["synthetic", "pluggy"]
CaptureKind = Literal["full", "incremental", "pending", "partial", "deletions"]
SHA256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
SCOPED = {"transactions", "bills", "investment_movements", "transaction_deletions"}
PROVIDER_ENDPOINTS = {
    "items": "/items/{id}",
    "resources": "/items/{id}/resources",
    "transactions": "/v2/transactions",
    "investment_movements": "/investments/{id}/transactions",
    "transaction_deletions": "event:transactions/deleted",
}


def object_key(
    run_id: UUID, date: str, resource: str, part: int, source: Source = "synthetic"
) -> str:
    return (
        f"bronze/source={source}/resource={resource}/ingestion_date={date}/"
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
    scope_id: UUID | None = None


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest_version: Literal[1, 2] = 1
    run_id: UUID
    source: Source = "synthetic"
    item_alias: str
    retrieved_at_utc: AwareDatetime
    reference_from: date
    reference_to: date
    collector_version: Literal["0.1.0"] = "0.1.0"
    consent_state: Literal["synthetic", "observed", "pending", "unknown"] = "synthetic"
    status: Literal["complete"] = "complete"
    objects: tuple[BronzeObject, ...] = Field(min_length=1, max_length=128)
    capture_kind: CaptureKind | None = None

    @model_validator(mode="after")
    def validate_capture(self):
        synthetic = self.source == "synthetic"
        alias = r"synthetic-[a-z][a-z0-9-]{0,23}" if synthetic else r"item-[a-f0-9]{32}"
        if not re.fullmatch(alias, self.item_alias):
            raise ValueError("Invalid capture alias")
        if synthetic:
            if (self.manifest_version, self.consent_state, self.capture_kind) != (
                1,
                "synthetic",
                None,
            ):
                raise ValueError("Invalid synthetic manifest version or state")
        elif (
            self.manifest_version != 2 or self.consent_state == "synthetic" or not self.capture_kind
        ):
            raise ValueError("Invalid provider manifest version or state")
        if not synthetic:
            resources = [item.resource for item in self.objects]
            if self.capture_kind == "deletions":
                if resources != ["transaction_deletions"]:
                    raise ValueError("Deletion captures contain a single event")
            elif resources.count("items") != 1 or "transaction_deletions" in resources:
                raise ValueError("Provider sync requires exactly one item observation")
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
                self.source,
            )
            identity = object_identity(
                self.run_id, item.resource, item.part_number, item.raw_sha256
            )
            if item.object_key != expected or item.object_id != identity or expected in keys:
                raise ValueError("Invalid object identity or layout")
            endpoint = f"/{item.resource}"
            if synthetic:
                if (
                    item.resource in ("items", "resources", "transaction_deletions")
                    or item.scope_id
                ):
                    raise ValueError("Invalid synthetic resource or scope")
            else:
                endpoint = PROVIDER_ENDPOINTS.get(item.resource, endpoint)
                if (item.resource in SCOPED) != (item.scope_id is not None):
                    raise ValueError("Invalid provider scope")
            if item.source_endpoint != endpoint:
                raise ValueError("Endpoint must not contain identifiers or query strings")
            keys.add(expected)
            total += item.raw_size_bytes
        if total > 32 * 1024 * 1024:
            raise ValueError("Capture exceeds the supported batch size")
        return self

    def to_bytes(self) -> bytes:
        return json_bytes(self.model_dump(mode="json", exclude_none=True))


def schema_fingerprint(value: object) -> str:
    def shape(item):
        if isinstance(item, dict):
            return {key: shape(child) for key, child in sorted(item.items())}
        if isinstance(item, list):
            return sorted({json_bytes(shape(child)).decode() for child in item})
        return type(item).__name__

    return hashlib.sha256(json_bytes(shape(value))).hexdigest()
