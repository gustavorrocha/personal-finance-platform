"""Collect one bounded observation from an existing provider item."""

from datetime import UTC, date, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from finance_lake.bronze import BronzeLake, CapturePage
from finance_lake.manifest import CaptureKind, Manifest, Resource
from finance_pluggy.client import AuditError, Pluggy, Unavailable
from finance_pluggy.coverage import identifier

CREATION_OVERLAP = timedelta(days=2)
RECENT_WINDOW = timedelta(days=45)


def item_key(item_id: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"finance:pluggy:item:{identifier(item_id)}")


def entity_key(item: UUID, resource: str, provider_id: str, scope: UUID | None = None) -> UUID:
    return uuid5(scope or item, f"{resource}:{provider_id}")


def collect(
    client: Pluggy,
    lake: BronzeLake,
    item_id: str,
    run_id: UUID,
    observed: datetime,
    checkpoint: tuple[datetime, set[UUID]] | None,
) -> Manifest:
    item = item_key(item_id)
    item_page = client.item_page(item_id)
    connector = item_page.data.get("connector")
    if identifier(item_page.data.get("id")) != item_id or not isinstance(connector, dict):
        raise AuditError("Invalid provider item response.")
    pages = [CapturePage("items", item_page.raw)]
    size = len(item_page.raw)
    incomplete = False

    def read(resource: Resource, path: str, scope: UUID | None = None, **filters: str):
        nonlocal size, incomplete
        start = len(pages)
        try:
            for page in client.pages(path, **filters):
                size += len(page.raw)
                if len(pages) >= 128 or size > 32 * 1024 * 1024:
                    raise AuditError("Provider capture exceeded the batch limit.")
                pages.append(CapturePage(resource, page.raw, scope))
                yield from page.data["results"]
        except Unavailable:
            if len(pages) != start:
                raise
            incomplete = True

    status = item_page.data.get("status")
    kind: CaptureKind = "incremental" if checkpoint else "full"
    reference_from = observed.date() - RECENT_WINDOW if checkpoint else date(1970, 1, 1)
    resources = list(read("resources", f"/items/{item_id}/resources"))
    if status not in ("UPDATED", "PARTIAL_SUCCESS"):
        kind = "pending"
    else:
        incomplete |= (
            status == "PARTIAL_SUCCESS"
            or item_page.data.get("hasResourcesPendingAuthorization") is True
            or any(row.get("status") == "PENDING_AUTHORISATION" for row in resources)
        )
        products = connector.get("products")

        def supports(*expected: str) -> bool:
            return (
                not products
                or not isinstance(products, list)
                or any(product in products for product in expected)
            )

        if supports("ACCOUNTS", "CREDIT_CARDS", "TRANSACTIONS"):
            accounts = {
                identifier(row.get("id")): row.get("type")
                for row in read("accounts", "/accounts", itemId=item_id)
            }
            for account, account_type in accounts.items():
                scope = entity_key(item, "accounts", account)
                if supports("TRANSACTIONS", "CREDIT_CARDS"):
                    windows: list[dict[str, str]] = [{}]
                    if checkpoint and scope in checkpoint[1]:
                        since = (checkpoint[0] - CREATION_OVERLAP).astimezone(UTC)
                        windows = [
                            {
                                "createdAtFrom": since.isoformat(timespec="milliseconds").replace(
                                    "+00:00", "Z"
                                )
                            },
                            {"dateFrom": reference_from.isoformat()},
                        ]
                    for filters in windows:
                        for row in read(
                            "transactions", "/v2/transactions", scope, accountId=account, **filters
                        ):
                            if identifier(row.get("accountId")) != account:
                                raise AuditError("Transaction escaped its account scope.")
                if account_type == "CREDIT":
                    for _ in read("bills", "/bills", scope, accountId=account):
                        pass
        if supports("INVESTMENTS", "INVESTMENTS_TRANSACTIONS"):
            investments = {
                identifier(row.get("id"))
                for row in read("investments", "/investments", itemId=item_id)
            }
            if supports("INVESTMENTS_TRANSACTIONS"):
                for investment in sorted(investments):
                    scope = entity_key(item, "investments", investment)
                    for _ in read(
                        "investment_movements", f"/investments/{investment}/transactions", scope
                    ):
                        pass
        if incomplete:
            kind = "partial"
    return lake.commit(
        run_id=run_id,
        retrieved_at=observed,
        item_alias=f"item-{item.hex}",
        payloads=pages,
        capture_kind=kind,
        reference_from=reference_from,
    )
