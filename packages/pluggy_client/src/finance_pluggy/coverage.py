"""Aggregate existing consent data into a redacted report without persistence."""

import json
import logging
import os
import re
from collections import Counter
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from datetime import date, datetime
from uuid import UUID

import httpx

from .client import AuditError, Pluggy, Unavailable

ITEM_STATES = (
    "CREATED",
    "UPDATING",
    "UPDATED",
    "LOGIN_ERROR",
    "WAITING_USER_INPUT",
    "OUTDATED",
    "ERROR",
    "PARTIAL_SUCCESS",
)
RESOURCE_STATES = ("AVAILABLE", "UNAVAILABLE", "TEMPORARILY_UNAVAILABLE", "PENDING_AUTHORISATION")
PRODUCTS = ("ACCOUNTS", "CREDIT_CARDS", "TRANSACTIONS", "INVESTMENTS", "INVESTMENTS_TRANSACTIONS")
POT_NAME = re.compile(r"\b(?:cofrinhos?|caixinhas?)\b", re.IGNORECASE)


def identifier(value: object) -> str:
    if isinstance(value, str):
        try:
            return str(UUID(value.strip()))
        except ValueError:
            pass
    raise AuditError("Missing or invalid Pluggy identifier.")


def month(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        day = (
            date.fromisoformat(value) if len(value) == 10 else datetime.fromisoformat(value).date()
        )
    except ValueError:
        return None
    return day.isoformat()[:7]


def measure(
    scopes: Iterable[Iterable[dict]],
    date_field: str | None = None,
    observe: Callable[[dict], None] | None = None,
) -> dict:
    count = read = unavailable = dated = 0
    first = last = None
    for records in scopes:
        try:
            for record in records:
                count += 1
                if observe is not None:
                    observe(record)
                if date_field and (period := month(record.get(date_field))):
                    first = period if first is None else min(first, period)
                    last = period if last is None else max(last, period)
                    dated += 1
            read += 1
        except Unavailable:
            unavailable += 1
    if unavailable:
        status = "partial" if read or count else "unavailable"
    else:
        status = "observed" if count else ("empty" if read else "no_scope")
    result = {
        "status": status,
        "count": count,
        "scopes_read": read,
        "scopes_unavailable": unavailable,
    }
    if date_field:
        result.update(first_month=first, last_month=last, dated_count=dated)
    return result


def audit_source(client: Pluggy, source: str, item_id: str) -> dict:
    try:
        item = client.item(item_id)
    except Unavailable:
        return {"source": source, "item_status": "unavailable"}
    connector = item.get("connector")
    if not isinstance(connector, dict) or identifier(item.get("id")) != item_id:
        raise AuditError("Invalid Pluggy item response.")
    status = item.get("status")
    products = connector.get("products")
    pending = item.get("hasResourcesPendingAuthorization")
    resources = Counter()
    accounts = {}
    investments = set()
    pots = 0

    def resource(row: dict) -> None:
        value = row.get("status")
        resources[value if value in RESOURCE_STATES else "unknown"] += 1

    def save_pot(row: dict) -> None:
        nonlocal pots
        if any(
            isinstance(value, str) and POT_NAME.search(value)
            for value in (row.get("name"), row.get("marketingName"))
        ):
            pots += 1

    def account(row: dict) -> None:
        key = identifier(row.get("id"))
        if key not in accounts:
            accounts[key] = row.get("type") == "CREDIT"
            save_pot(row)

    def investment(row: dict) -> None:
        key = identifier(row.get("id"))
        if key not in investments:
            investments.add(key)
            save_pot(row)

    resource_report = measure([client.records(f"/items/{item_id}/resources")], observe=resource)
    account_report = measure([client.records("/accounts", itemId=item_id)], observe=account)
    investment_report = measure(
        [client.records("/investments", itemId=item_id)], "date", investment
    )
    cards = [key for key, is_card in accounts.items() if is_card]
    report = {
        "source": source,
        "item_status": status if status in ITEM_STATES else "unknown",
        "connector_id": connector.get("id") if type(connector.get("id")) is int else None,
        "open_finance": connector.get("isOpenFinance") is True,
        "connector_products": (
            [product for product in PRODUCTS if product in products]
            if isinstance(products, list)
            else None
        ),
        "consent_expires_month": month(item.get("consentExpiresAt")),
        "last_sync_month": month(item.get("lastUpdatedAt")),
        "resources_collected_month": month(item.get("resourcesCollectedAt")),
        "resources_pending_authorization": pending if type(pending) is bool else None,
        "resources": {**resource_report, "status_counts": dict(resources)},
        "accounts": {**account_report, "credit_cards": len(cards)},
        "investments": investment_report,
        "transactions": measure(
            (client.records("/v2/transactions", accountId=key) for key in accounts), "date"
        ),
        "bills": measure((client.records("/bills", accountId=key) for key in cards), "dueDate"),
        "investment_movements": measure(
            (client.records(f"/investments/{key}/transactions") for key in sorted(investments)),
            "date",
        ),
    }
    complete = all(
        r["status"] in ("observed", "empty") for r in (account_report, investment_report)
    )
    report["savings_pots"] = {
        "name_matches": pots,
        "status": "candidate" if pots else ("not_observed" if complete else "inconclusive"),
    }
    return report


@contextmanager
def configured_client(max_pages: int):
    names = ("PLUGGY_CLIENT_ID", "PLUGGY_CLIENT_SECRET", "PLUGGY_ITEM_IDS")
    missing = [name for name in names if not os.environ.get(name, "").strip()]
    if missing:
        raise AuditError("Configure the following environment variables: " + ", ".join(missing))
    client_id, secret, configured_items = (os.environ[name].strip() for name in names)
    try:
        values = json.loads(configured_items)
    except (ValueError, RecursionError):
        raise AuditError("PLUGGY_ITEM_IDS must be a JSON array of item UUIDs.") from None
    if not isinstance(values, list) or not values:
        raise AuditError("PLUGGY_ITEM_IDS must be a nonempty JSON array of item UUIDs.")
    items = [identifier(value) for value in values]
    if len(set(items)) != len(items):
        raise AuditError("PLUGGY_ITEM_IDS must contain unique item UUIDs.")
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    with httpx.Client(timeout=15, trust_env=False) as http:
        client = Pluggy(http, max_pages)
        client.authenticate(identifier(client_id), secret)
        yield client, items


def audit_from_environment(max_pages: int) -> dict:
    with configured_client(max_pages) as (client, items):
        return {
            "redacted": True,
            "sources": [
                audit_source(client, f"item-{index}", item_id)
                for index, item_id in enumerate(items, start=1)
            ],
        }
