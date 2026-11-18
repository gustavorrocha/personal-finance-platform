"""Create a repeatable synthetic observation using the regular Bronze-to-Silver path."""

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from finance_lake.bronze import CapturePage
from finance_lake.manifest import json_bytes

from .collection import entity_key, item_key
from .silver import SilverWarehouse

DEMO_SOURCE = "10000000-0000-4000-8000-100000000001"
DEMO_ACCOUNT = "10000000-0000-4000-8000-100000000002"


def load_demo(silver: SilverWarehouse) -> int:
    item = item_key(DEMO_SOURCE)
    account = entity_key(item, "accounts", DEMO_ACCOUNT)
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
    manifest = silver.lake.commit(
        run_id=uuid5(NAMESPACE_URL, "finance:spending-demo-v1"),
        retrieved_at=datetime(2026, 11, 17, tzinfo=UTC),
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
            CapturePage(
                "accounts", json_bytes({"results": [{"id": DEMO_ACCOUNT, "type": "CREDIT"}]})
            ),
            CapturePage("transactions", json_bytes({"results": rows, "next": None}), account),
        ],
    )
    return silver.replay(manifest.run_id)
