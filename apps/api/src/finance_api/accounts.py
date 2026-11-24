"""Read-only, connection-scoped account snapshots and balance history."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict

from .spending import DEMO_ITEM, add_institutions, dashboard_query, same_origin

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
    await add_institutions(connections)
    selected = select_connection(connections, item, "Connection has no reported accounts")
    rows = []
    if selected is not None:
        rows = await dashboard_query(
            "SELECT account_key AS id, account_type AS type, subtype, currency, "
            "toString(balance) AS balance, "
            "concat(replaceOne(toString(observed_at), ' ', 'T'), 'Z') AS observed_at, "
            "name, number_suffix, brand, level, toString(credit_limit) AS credit_limit, "
            "toString(available_credit) AS available_credit, "
            "toString(minimum_payment) AS minimum_payment, "
            "toString(due_date) AS due_date, toString(close_date) AS close_date, disabled "
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


@router.get("/api/accounts/history")
async def account_history(
    item: UUID,
    account: UUID,
    limit: Annotated[int, Query(ge=1, le=SNAPSHOT_LIMIT)] = 90,
):
    rows = await dashboard_query(
        "SELECT concat(replaceOne(toString(history.observed_at), ' ', 'T'), 'Z') AS observed_at, "
        "currency, toString(balance) AS balance FROM analytics.account_balance_history AS history "
        "WHERE item_key = {item:UUID} AND account_key = {account:UUID} "
        "ORDER BY history.observed_at DESC LIMIT {limit:UInt16} FORMAT JSONEachRow",
        item=str(item),
        account=str(account),
        limit=str(limit + 1),
    )
    if not rows:
        raise HTTPException(404, "Account has no reported history in this connection")
    return {
        "observations": rows[:limit],
        "truncated": len(rows) > limit,
    }


class AccountSetting(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item: UUID
    disabled: bool


@router.put(
    "/api/accounts/{account}/disabled", status_code=204, dependencies=[Depends(same_origin)]
)
async def disable_account(account: UUID, setting: AccountSetting) -> Response:
    """A disabled account leaves balance totals and spending until it is enabled again."""
    known = await dashboard_query(
        "SELECT 1 FROM analytics.accounts_dashboard "
        "WHERE item_key = {item:UUID} AND account_key = {account:UUID} FORMAT JSONEachRow",
        item=str(setting.item),
        account=str(account),
    )
    if not known:
        raise HTTPException(404, "Account is not reported in this connection")
    await dashboard_query(
        "INSERT INTO core.account_settings (item_key, account_key, disabled) "
        "SELECT {item:UUID}, {account:UUID}, {disabled:Bool}",
        item=str(setting.item),
        account=str(account),
        disabled=str(setting.disabled).lower(),
    )
    return Response(status_code=204)
