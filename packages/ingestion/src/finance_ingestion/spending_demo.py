"""Create a repeatable synthetic observation using the regular Bronze-to-Silver path."""

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from finance_lake.bronze import CapturePage
from finance_lake.manifest import json_bytes

from .collection import entity_key, item_key
from .silver import SilverWarehouse

DEMO_SOURCE = "10000000-0000-4000-8000-100000000001"
DEMO_ACCOUNT = "10000000-0000-4000-8000-100000000002"
REVIEW_ACCOUNT = "10000000-0000-4000-8000-100000000003"


def load_demo(silver: SilverWarehouse) -> int:
    item = item_key(DEMO_SOURCE)
    inputs = (
        (15, "West Market", 84.23, "Groceries", "DEBIT", "", "POSTED"),
        (14, "Juniper Cafe", 27.60, "Restaurants", "DEBIT", "", "POSTED"),
        (12, "Metro Pass", 48.00, "Transport", "DEBIT", "", "POSTED"),
        (11, "West Market", 12.50, "", "CREDIT", "ESTORNO", "POSTED"),
        (10, "Corner Bookshop", 36.00, "", "DEBIT", "", "POSTED"),
        (6, "Garden Cinema", 32.00, "Entertainment", "DEBIT", "", "POSTED"),
        (5, "West Market", 41.70, "Groceries", "DEBIT", "", "POSTED"),
        (3, "Museum Studio", 22.00, "Entertainment", "DEBIT", "", "PENDING"),
        (1, "Card statement", 160.00, "", "DEBIT", "PAGAMENTO_FATURA", "POSTED"),
    )
    rows = [
        {
            "id": str(uuid5(item, str(index))),
            "accountId": DEMO_ACCOUNT,
            "date": f"2026-11-{day:02d}",
            "currencyCode": "BRL",
            "merchant": {"name": merchant},
            "amount": amount,
            "category": category,
            "operationType": operation,
            "status": status,
            "type": direction,
            "creditCardMetadata": {},
        }
        for index, (day, merchant, amount, category, direction, operation, status) in enumerate(
            inputs
        )
    ]
    review_rows = [
        {
            "id": str(uuid5(item, "review-" + str(index))),
            "accountId": REVIEW_ACCOUNT,
            "date": "2026-11-13",
            "currencyCode": "BRL",
            "merchant": {"name": name},
            "amount": amount,
            "operationType": operation,
            "status": status,
            "type": "DEBIT",
        }
        for index, (name, amount, operation, status) in enumerate(
            (
                ("Harbor Books", 23.50, "PIX", "POSTED"),
                ("Synthetic transfer", 40.00, "TRANSFER", "POSTED"),
                ("Pending debit", 11.00, "", "PENDING"),
            )
        )
    ]
    card_count = publish_demo(silver, item, DEMO_ACCOUNT, "CREDIT", "spending-demo-v1", rows)
    return card_count + publish_demo(
        silver, item, REVIEW_ACCOUNT, "BANK", "spending-demo-review-v1", review_rows
    )


def publish_demo(
    silver: SilverWarehouse,
    item: UUID,
    account: str,
    account_type: str,
    name: str,
    rows: list[dict],
) -> int:
    return commit_demo(
        silver,
        item,
        name,
        datetime(2026, 11, 17, tzinfo=UTC),
        [
            CapturePage(
                "accounts", json_bytes({"results": [{"id": account, "type": account_type}]})
            ),
            CapturePage(
                "transactions",
                json_bytes({"results": rows, "next": None}),
                entity_key(item, "accounts", account),
            ),
        ],
    )


def load_account_demo(silver: SilverWarehouse) -> int:
    item = item_key(DEMO_SOURCE)
    previous = [
        {"id": REVIEW_ACCOUNT, "type": "BANK", "balance": 1700.50, "currencyCode": "BRL"},
        {"id": DEMO_ACCOUNT, "type": "CREDIT", "balance": 0, "currencyCode": "BRL"},
    ]
    previous_count = commit_demo(
        silver,
        item,
        "account-demo-history-v1",
        datetime(2026, 11, 17, tzinfo=UTC),
        [CapturePage("accounts", json_bytes({"results": previous}))],
    )
    accounts = [
        {"id": REVIEW_ACCOUNT, "type": "BANK", "balance": 1850.75, "currencyCode": "BRL"},
        {"id": DEMO_ACCOUNT, "type": "CREDIT", "balance": -320.40, "currencyCode": "BRL"},
        {"id": "10000000-0000-4000-8000-100000000004", "type": "BANK", "currencyCode": "USD"},
    ]
    return previous_count + commit_demo(
        silver,
        item,
        "account-demo-v1",
        datetime(2026, 11, 18, tzinfo=UTC),
        [CapturePage("accounts", json_bytes({"results": accounts}))],
    )


def load_investment_demo(silver: SilverWarehouse) -> int:
    item = item_key(DEMO_SOURCE)
    positions = [
        {
            "id": str(uuid5(item, "investment-demo-equity")),
            "code": "DEMO11",
            "type": "EQUITY",
            "currencyCode": "BRL",
            "amount": 120.25,
            "balance": 115.20,
            "quantity": 5,
            "value": 24.05,
            "date": "2026-11-17",
        },
        {
            "id": str(uuid5(item, "investment-demo-fixed-income")),
            "type": "FIXED_INCOME",
            "currencyCode": "BRL",
            "amount": 800,
            "date": "2026-11-17",
            "dueDate": "2028-11-17",
        },
    ]
    return commit_demo(
        silver,
        item,
        "investment-demo-v1",
        datetime(2026, 11, 18, tzinfo=UTC),
        [CapturePage("investments", json_bytes({"results": positions}))],
    )


def commit_demo(
    silver: SilverWarehouse, item: UUID, name: str, observed: datetime, pages: list[CapturePage]
) -> int:
    manifest = silver.lake.commit(
        run_id=uuid5(NAMESPACE_URL, f"finance:{name}"),
        retrieved_at=observed,
        item_alias=f"item-{item.hex}",
        capture_kind="full",
        payloads=[
            CapturePage(
                "items",
                json_bytes(
                    {
                        "id": DEMO_SOURCE,
                        "status": "UPDATED",
                        "connector": {"id": 999999},
                    }
                ),
            ),
            *pages,
        ],
    )
    return silver.replay(manifest.run_id)
