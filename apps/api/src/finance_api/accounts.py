"""Read-only, connection-scoped account snapshots."""

from uuid import UUID

from fastapi import APIRouter, HTTPException

from .spending import DEMO_ITEM, dashboard_query

router = APIRouter()
SNAPSHOT_LIMIT = 200


def select_connection(connections: list[dict], item: UUID | None, unavailable: str) -> dict | None:
    for index, connection in enumerate(connections, start=1):
        connection["is_demo"] = connection["id"] == DEMO_ITEM
        connection["label"] = "Synthetic demo" if connection["is_demo"] else f"Connection {index}"
    if item is None:
        return connections[0] if len(connections) == 1 else None
    selected = next(
        (connection for connection in connections if connection["id"] == str(item)), None
    )
    if selected is None:
        raise HTTPException(404, unavailable)
    return selected


@router.get("/api/accounts")
async def account_snapshot(item: UUID | None = None):
    connections = await dashboard_query(
        "SELECT item_key AS id FROM analytics.accounts_dashboard "
        "GROUP BY item_key ORDER BY item_key FORMAT JSONEachRow"
    )
    selected = select_connection(connections, item, "Connection has no reported accounts")
    rows = []
    if selected is not None:
        rows = await dashboard_query(
            "SELECT account_key AS id, account_type AS type, subtype, currency, "
            "toString(balance) AS balance, "
            "concat(replaceOne(toString(observed_at), ' ', 'T'), 'Z') AS observed_at "
            "FROM analytics.accounts_dashboard WHERE item_key = {item:UUID} "
            f"ORDER BY account_key LIMIT {SNAPSHOT_LIMIT + 1} FORMAT JSONEachRow",
            item=selected["id"],
        )
    return {
        "connections": connections,
        "selected": selected,
        "accounts": rows[:SNAPSHOT_LIMIT],
        "truncated": len(rows) > SNAPSHOT_LIMIT,
    }
