"""Publish typed, versioned provider observations after verified Bronze replay."""

import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation, localcontext
from uuid import UUID

from finance_lake.bronze import ReplayRecord
from finance_lake.manifest import Manifest, json_bytes
from finance_pluggy.coverage import identifier

from .collection import entity_key, item_key
from .spending import spending_fields
from .warehouse import BronzeWarehouse, Execute


def sql_time(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")


def text_field(value: object, limit: int = 128) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > limit or not value.isprintable():
        raise ValueError("Invalid provider text field")
    return value


def provider_date(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Invalid provider date")
    parsed = date.fromisoformat(value) if len(value) == 10 else datetime.fromisoformat(value).date()
    # ClickHouse Date has a narrower range than Python dates.
    if not 0 <= (parsed - date(1970, 1, 1)).days <= 65535:
        raise ValueError("Provider date outside the supported range")
    return parsed.isoformat()


def decimal_field(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise ValueError("Invalid provider decimal")
    number = Decimal(value)
    with localcontext() as context:
        context.prec = 40
        if not number.is_finite() or abs(number) >= Decimal("1e26"):
            raise ValueError("Provider decimal outside the supported range")
        try:
            normalized = number.quantize(Decimal("1e-12"))
        except InvalidOperation:
            raise ValueError("Provider decimal outside the supported range") from None
        if abs(normalized) >= Decimal("1e26"):
            raise ValueError("Rounded decimal outside the supported range")
    return format(normalized, "f")


def transaction_details(record: dict) -> dict:
    metadata = record.get("creditCardMetadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    description = record.get("descriptionRaw")
    if not isinstance(description, str) or not description.strip():
        description = record.get("description")
    category = record.get("category")
    transaction_time = None
    reported = record.get("date")
    if isinstance(reported, str) and len(reported) > 10:
        timestamp = datetime.fromisoformat(reported)
        if timestamp.tzinfo is not None and any(
            (timestamp.hour, timestamp.minute, timestamp.second, timestamp.microsecond)
        ):
            transaction_time = sql_time(timestamp)
    purchase_date = None
    try:
        purchase_date = provider_date(metadata.get("purchaseDate"))
    except ValueError:
        pass
    installments = {}
    for field, key in (
        ("installment_number", "installmentNumber"),
        ("total_installments", "totalInstallments"),
    ):
        value = metadata.get(key)
        installments[field] = value if type(value) is int and 1 <= value <= 65535 else None
    purchase_amount = None
    try:
        purchase_amount = decimal_field(metadata.get("totalAmount"))
    except ValueError:
        pass
    return {
        "bank_description": description[:1024] if isinstance(description, str) else "",
        "bank_category": category[:256] if isinstance(category, str) else "",
        "transaction_time": transaction_time,
        "original_purchase_date": purchase_date,
        "installment_total_amount": purchase_amount,
        **installments,
    }


def normalized_row(
    manifest: Manifest, item: UUID, entry: ReplayRecord, ordinal: int, cards: set[UUID]
) -> dict:
    record = entry.record
    resource = entry.resource
    deleted = resource == "transaction_deletions"
    if deleted:
        resource = "transactions"
    if resource == "resources":
        provider_id = text_field(record.get("resourceId"), 512)
        if not provider_id:
            raise ValueError("Missing provider resource identity")
    else:
        provider_id = identifier(record.get("id"))
    key = item if resource == "items" else entity_key(item, resource, provider_id, entry.scope_id)
    row = {
        "run_id": str(manifest.run_id),
        "object_id": str(entry.object_id),
        "record_id": str(entry.record_id),
        "row_order": ordinal,
        "item_key": str(item),
        "entity_key": str(key),
        "resource": resource,
        "scope_id": str(entry.scope_id) if entry.scope_id else None,
        "observed_at": sql_time(manifest.retrieved_at_utc),
        "deleted": deleted,
    }
    if deleted:
        return row
    if resource == "items":
        if item_key(provider_id) != item:
            raise ValueError("Item does not match its capture scope")
        connector = record.get("connector")
        connector_id = connector.get("id") if isinstance(connector, dict) else None
        if type(connector_id) is not int or not 0 < connector_id < 2**32:
            raise ValueError("Invalid connector identity")
        expires = record.get("consentExpiresAt")
        if expires is not None:
            if not isinstance(expires, str):
                raise ValueError("Invalid consent expiration time")
            expires = datetime.fromisoformat(expires)
            if expires.tzinfo is None:
                raise ValueError("Missing consent expiration time zone")
        row["connector_id"] = connector_id
        row["consent_expires_at"] = sql_time(expires) if expires is not None else None
    row["status"] = text_field(record.get("status"))
    row["type"] = text_field(record.get("type"))
    row["subtype"] = text_field(record.get("subtype"))
    currency = record.get("totalAmountCurrencyCode" if resource == "bills" else "currencyCode")
    if currency is not None and (
        not isinstance(currency, str) or not re.fullmatch("[A-Z]{3}", currency)
    ):
        raise ValueError("Invalid provider currency")
    row["currency"] = currency
    for column, field in (
        ("economic_date", "date"),
        ("due_date", "dueDate"),
        ("trade_date", "tradeDate"),
        ("issue_date", "issueDate"),
    ):
        row[column] = provider_date(record.get(field))
    for column, field in (
        ("amount", "totalAmount" if resource == "bills" else "amount"),
        ("balance", "balance"),
        ("quantity", "quantity"),
        ("unit_value", "value"),
        ("rate", "rate"),
    ):
        row[column] = decimal_field(record.get(field))
    if resource == "transactions" and any(
        row[column] is None for column in ("amount", "economic_date", "currency")
    ):
        raise ValueError("Incomplete transaction")
    if resource == "transactions":
        row.update(spending_fields(record, str(key), card_account=entry.scope_id in cards))
        row.update(transaction_details(record))
    if resource == "investments":
        row["rate_type"] = text_field(record.get("rateType"))
        row["symbol"] = text_field(record.get("code"))
        row["isin"] = text_field(record.get("isin"))
    return row


class SilverWarehouse:
    def __init__(self, bronze: BronzeWarehouse, execute: Execute):
        self.bronze = bronze
        self.lake = bronze.lake
        self.execute = execute

    def append(self, table: str, rows: list[dict]) -> None:
        if rows:
            self.execute(
                f"INSERT INTO {table} FORMAT JSONEachRow",
                native=b"\n".join(json_bytes(row) for row in rows) + b"\n",
            )

    def event(self, run_id: UUID, item: UUID, event: str) -> None:
        self.append(
            "metadata.ingestion_run_events",
            [
                {
                    "run_id": str(run_id),
                    "item_key": str(item),
                    "event": event,
                    "recorded_at": sql_time(datetime.now(UTC)),
                }
            ],
        )

    def checkpoint(self, item: UUID) -> tuple[datetime, set[UUID]] | None:
        output = self.execute(
            "SELECT observed_at, accounts FROM metadata.sync_checkpoints_current "
            f"WHERE item_key = toUUID('{item}') FORMAT JSONEachRow"
        )
        if not output.strip():
            return None
        state = json.loads(output)
        return datetime.fromisoformat(state["observed_at"]).replace(tzinfo=UTC), {
            UUID(account) for account in state["accounts"]
        }

    def knows_account(self, item: UUID, account: UUID) -> bool:
        output = self.execute(
            "SELECT count() FROM core.provider_observations "
            f"WHERE resource = 'accounts' AND item_key = toUUID('{item}') "
            f"AND entity_key = toUUID('{account}') FORMAT TSV"
        )
        return int(output) > 0

    def replay(self, run_id: UUID) -> int:
        run_id = UUID(str(run_id))
        self.bronze.index_run(run_id, source="pluggy")
        manifest = self.lake.read_manifest(run_id)
        if manifest.source != "pluggy":
            raise ValueError("Silver replay requires provider Bronze")
        item = UUID(manifest.item_alias.removeprefix("item-"))
        entries = list(self.lake.replay(run_id))
        cards = {
            entity_key(item, "accounts", identifier(entry.record.get("id")))
            for entry in entries
            if entry.resource == "accounts" and entry.record.get("type") == "CREDIT"
        }
        rows = [
            normalized_row(manifest, item, entry, ordinal, cards)
            for ordinal, entry in enumerate(entries)
        ]
        self.append("core.provider_versions", rows)
        self.append(
            "metadata.ingestion_publications",
            [
                {
                    "run_id": str(run_id),
                    "item_key": str(item),
                    "observed_at": sql_time(manifest.retrieved_at_utc),
                    "kind": manifest.capture_kind,
                    "accounts": sorted(
                        {row["entity_key"] for row in rows if row["resource"] == "accounts"}
                    ),
                    "record_count": len(rows),
                }
            ],
        )
        return len(rows)
