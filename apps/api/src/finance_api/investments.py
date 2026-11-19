"""Read-only, connection-scoped investment positions."""

from uuid import UUID

from fastapi import APIRouter

from .accounts import SNAPSHOT_LIMIT, select_connection
from .spending import dashboard_query

router = APIRouter()


@router.get("/api/investments")
async def investment_snapshot(item: UUID | None = None):
    connections = await dashboard_query(
        "SELECT item_key AS id FROM analytics.investments_dashboard "
        "GROUP BY item_key ORDER BY item_key FORMAT JSONEachRow"
    )
    selected = select_connection(connections, item, "Connection has no reported investments")
    rows = []
    if selected is not None:
        rows = await dashboard_query(
            "SELECT position_key AS id, ticker, name, position_type AS type, subtype, status, "
            "currency, "
            "toString(indexer_percentage) AS indexer_percentage, indexer, "
            "toString(net_balance) AS net_balance, toString(gross_amount) AS gross_amount, "
            "toString(quantity) AS quantity, toString(unit_price) AS unit_price, "
            "reference_date, maturity_date, "
            "concat(replaceOne(toString(observed_at), ' ', 'T'), 'Z') AS observed_at "
            "FROM analytics.investments_dashboard WHERE item_key = {item:UUID} "
            f"ORDER BY position_key LIMIT {SNAPSHOT_LIMIT + 1} FORMAT JSONEachRow",
            item=selected["id"],
        )
    return {
        "connections": connections,
        "selected": selected,
        "positions": rows[:SNAPSHOT_LIMIT],
        "truncated": len(rows) > SNAPSHOT_LIMIT,
    }
