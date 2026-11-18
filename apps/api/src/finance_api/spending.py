"""Same-origin dashboard access to a narrow ClickHouse projection."""

import json
from datetime import date
from pathlib import Path
from typing import Annotated, Literal, get_args
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict

router = APIRouter(prefix="/api/spending")
ORIGINS = {"http://localhost:8080", "http://127.0.0.1:8080"}
DEMO_ITEM = "77b7ff50-da90-5c0d-b938-f4af43c8b6de"
Category = Literal[
    "Groceries",
    "Dining",
    "Transport",
    "Home",
    "Shopping",
    "Health",
    "Leisure",
    "Uncategorized",
]


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item: UUID
    transaction: UUID
    category: Category


async def dashboard_query(query: str, **parameters: str) -> list[dict]:
    password = Path("/run/secrets/dashboard_password").read_text(encoding="utf-8").strip()
    async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
        response = await client.post(
            "http://clickhouse:8123/",
            params={f"param_{key}": value for key, value in parameters.items()},
            content=query,
            auth=("dashboard", password),
        )
        response.raise_for_status()
        return [json.loads(line) for line in response.text.splitlines()]


@router.get("")
async def spending(
    item: UUID | None = None,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
):
    if month is not None and not 1970 <= int(month[:4]) <= 2148:
        raise HTTPException(422, "Unsupported month")
    connections = await dashboard_query(
        "SELECT item_key AS id, formatDateTime(max(economic_date), '%Y-%m') AS latest_month "
        "FROM analytics.spending_current GROUP BY item_key ORDER BY item_key FORMAT JSONEachRow"
    )
    for index, row in enumerate(connections, start=1):
        row["label"] = "Synthetic demo" if row["id"] == DEMO_ITEM else f"Connection {index}"
    if item is None:
        selected = connections[0] if len(connections) == 1 else None
    else:
        selected = next((row for row in connections if row["id"] == str(item)), None)
        if selected is None:
            raise HTTPException(404, "Connection has no reported expenses")
    result = {
        "connections": connections,
        "selected": selected,
        "month": month,
        "totals": [],
        "expenses": [],
        "categories": get_args(Category),
    }
    if selected is None:
        return result
    month = month or selected["latest_month"]
    first = date.fromisoformat(f"{month}-01")
    filters = {"item": selected["id"], "start": first.isoformat()}
    where = "WHERE item_key = {item:UUID} AND toStartOfMonth(economic_date) = {start:Date} "
    result["month"] = month
    result["totals"] = await dashboard_query(
        "SELECT currency, if(grouping(category) = 1, NULL, category) AS bucket, "
        "toString(sum(net_amount)) AS total, count() AS entries "
        f"FROM analytics.spending_current {where}"
        "GROUP BY GROUPING SETS ((currency, category), (currency)) "
        "ORDER BY currency, bucket NULLS FIRST FORMAT JSONEachRow",
        **filters,
    )
    result["expenses"] = await dashboard_query(
        "SELECT transaction_key AS id, economic_date AS date, currency, "
        "toString(net_amount) AS amount, merchant_label AS merchant, category "
        f"FROM analytics.spending_current {where}"
        "ORDER BY date DESC, transaction_key DESC LIMIT 100 FORMAT JSONEachRow",
        **filters,
    )
    return result


def same_origin(request: Request) -> None:
    if request.headers.get("origin") not in ORIGINS:
        raise HTTPException(403, "Open the local dashboard to change a category")
    if request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
        raise HTTPException(415, "Expected JSON")


@router.post("/rules", status_code=204, dependencies=[Depends(same_origin)])
async def save_rule(rule: Rule) -> Response:
    where = "WHERE item_key = {item:UUID} AND transaction_key = {transaction:UUID} LIMIT 1 "
    scope = {"item": str(rule.item), "transaction": str(rule.transaction)}
    if not await dashboard_query(
        f"SELECT transaction_key FROM analytics.spending_current {where}FORMAT JSONEachRow", **scope
    ):
        raise HTTPException(404, "Expense is unavailable")
    await dashboard_query(
        "INSERT INTO core.spending_rules (item_key, merchant_key, category) "
        "SELECT item_key, merchant_key, {category:String} "
        f"FROM analytics.spending_current {where}",
        category=rule.category,
        **scope,
    )
    return Response(status_code=204)
