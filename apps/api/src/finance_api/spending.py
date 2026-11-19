"""Same-origin dashboard access to a narrow ClickHouse projection."""

import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Annotated, Literal, get_args
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from .local_classifier import (
    BATCH_LIMIT,
    MODEL_TIMEOUT,
    Category,
    ClassifierUnavailable,
    LocalClassifier,
)

router = APIRouter(prefix="/api/spending")
ORIGINS = {"http://localhost:8080", "http://127.0.0.1:8080"}
DEMO_ITEM = "77b7ff50-da90-5c0d-b938-f4af43c8b6de"
classifier = LocalClassifier()
EXPENSE_PAGE_SIZE = 100
# 12 charted months plus the month before them, so every month has a comparison.
HISTORY_MONTHS = 13
TRANSACTION_DETAILS = (
    "description, bank_category, "
    "concat(replaceOne(toString(transaction_time), ' ', 'T'), 'Z') AS transaction_time, "
    "original_purchase_date, installment_number, total_installments, "
    "toString(installment_total_amount) AS installment_total_amount, "
    "mcc, cnpj, cnae, business_name, merchant_category "
)


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item: UUID
    transaction: UUID
    category: Category


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item: UUID
    transaction: UUID
    decision: Literal["include", "exclude", "reset"]


class SuggestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item: UUID
    transactions: list[UUID] = Field(min_length=1, max_length=BATCH_LIMIT)


def month_start(index: int) -> date:
    return date(index // 12, index % 12 + 1, 1)


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
    item: UUID | Literal["all"] | None = None,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    search: Annotated[str, Query(max_length=120)] = "",
):
    if month is not None and not 1970 <= int(month[:4]) <= 2148:
        raise HTTPException(422, "Unsupported month")
    connections = await dashboard_query(
        "SELECT item_key AS id, formatDateTime("
        "if(countIf(posted) > 0, maxIf(economic_date, posted), "
        "least(max(economic_date), today())), "
        "'%Y-%m') AS latest_month "
        "FROM (SELECT item_key, economic_date, true AS posted FROM analytics.spending_dashboard "
        "UNION ALL SELECT item_key, economic_date, false AS posted "
        "FROM analytics.pending_card_spending) "
        "GROUP BY item_key ORDER BY item_key FORMAT JSONEachRow"
    )
    for index, row in enumerate(connections, start=1):
        row["is_demo"] = row["id"] == DEMO_ITEM
        row["label"] = "Synthetic demo" if row["is_demo"] else f"Connection {index}"
    combined = item == "all" and any(not row["is_demo"] for row in connections)
    if combined:
        selected = {
            "id": "all",
            "is_demo": False,
            "latest_month": max(row["latest_month"] for row in connections if not row["is_demo"]),
        }
    elif item is None or item == "all":
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
        "history": [],
        "investments": [],
        "invested": [],
        "expenses": [],
        "has_more_expenses": False,
        "reviews": [],
        "categories": get_args(Category),
    }
    if selected is None:
        return result
    month = month or selected["latest_month"]
    first = date.fromisoformat(f"{month}-01")
    filters = {"start": first.isoformat()}
    if combined:
        filters["demo"] = DEMO_ITEM
        scope = "item_key != {demo:UUID}"
    else:
        filters["item"] = selected["id"]
        scope = "item_key = {item:UUID}"
    where = f"WHERE {scope} AND toStartOfMonth(economic_date) = {{start:Date}} "
    result["month"] = month
    result["totals"] = await dashboard_query(
        "SELECT currency, if(grouping(category) = 1, NULL, category) AS bucket, "
        "toString(sum(net_amount)) AS total, count() AS entries "
        f"FROM analytics.spending_dashboard {where}AND included "
        "GROUP BY GROUPING SETS ((currency, category), (currency)) "
        "ORDER BY currency, bucket NULLS FIRST FORMAT JSONEachRow",
        **filters,
    )
    months = first.year * 12 + first.month - 1
    window = filters | {
        "since": max(month_start(months - HISTORY_MONTHS + 1), date(1970, 1, 1)).isoformat(),
        "until": month_start(months + 1).isoformat(),
    }
    in_window = (
        f"WHERE {scope} AND economic_date >= {{since:Date}} AND economic_date < {{until:Date}} "
    )
    result["history"] = await dashboard_query(
        "SELECT formatDateTime(toStartOfMonth(economic_date), '%Y-%m') AS month, currency, "
        "source, status, category, toString(sum(amount)) AS total, count() AS entries "
        "FROM (SELECT item_key, economic_date, currency, source, category, "
        "toDecimal128(net_amount, 12) AS amount, 'POSTED' AS status "
        "FROM analytics.spending_dashboard WHERE included "
        "UNION ALL SELECT item_key, economic_date, currency, 'card' AS source, category, "
        "toDecimal128(amount, 12) AS amount, 'PENDING' AS status "
        "FROM analytics.pending_card_spending) "
        f"{in_window}GROUP BY month, currency, source, status, category "
        "ORDER BY month, currency, source, status, category FORMAT JSONEachRow",
        **window,
    )
    result["investments"] = await dashboard_query(
        "SELECT formatDateTime(toStartOfMonth(economic_date), '%Y-%m') AS month, currency, "
        "kind, toString(sum(amount)) AS total, count() AS entries "
        f"FROM analytics.investment_flows {in_window}"
        "GROUP BY month, currency, kind ORDER BY month, currency, kind FORMAT JSONEachRow",
        **window,
    )
    # Latest reported balances, independent of the selected month.
    result["invested"] = await dashboard_query(
        "SELECT currency, source, toString(sum(balance)) AS total, "
        "toString(max(observed_on)) AS observed_on "
        f"FROM analytics.invested_balances WHERE {scope} "
        "GROUP BY currency, source ORDER BY currency, source FORMAT JSONEachRow",
        **filters,
    )
    search = search.strip()
    expense_filters = dict(filters, offset=str((page - 1) * EXPENSE_PAGE_SIZE))
    search_filter = ""
    if search:
        expense_filters["search"] = search
        search_filter = (
            "WHERE positionCaseInsensitiveUTF8(description, {search:String}) > 0 "
            "OR positionCaseInsensitiveUTF8(merchant, {search:String}) > 0 "
            "OR positionCaseInsensitiveUTF8(category, {search:String}) > 0 "
            "OR positionCaseInsensitiveUTF8(bank_category, {search:String}) > 0 "
        )
    details = (
        "item_key AS item, transaction_key AS id, economic_date AS date, currency, "
        "merchant_label AS merchant, category, " + TRANSACTION_DETAILS
    )
    expenses = await dashboard_query(
        f"SELECT * FROM (SELECT {details}, toString(net_amount) AS amount, "
        f"'POSTED' AS status FROM analytics.spending_dashboard {where}AND included "
        f"UNION ALL SELECT {details}, toString(amount) AS amount, "
        f"'PENDING' AS status FROM analytics.pending_card_spending {where}) "
        f"{search_filter}ORDER BY date DESC, transaction_time DESC, item, id "
        f"LIMIT {EXPENSE_PAGE_SIZE + 1} OFFSET {{offset:UInt32}} FORMAT JSONEachRow",
        **expense_filters,
    )
    result["expenses"] = expenses[:EXPENSE_PAGE_SIZE]
    result["has_more_expenses"] = len(expenses) > EXPENSE_PAGE_SIZE
    result["reviews"] = await dashboard_query(
        "SELECT item_key AS item, transaction_key AS id, economic_date AS date, currency, "
        "toString(net_amount) AS amount, merchant_label AS merchant, operation, decision, "
        f"{TRANSACTION_DETAILS}"
        f"FROM analytics.spending_dashboard {where}AND reviewable "
        "ORDER BY (decision != ''), date DESC, transaction_key DESC LIMIT 100 FORMAT JSONEachRow",
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
    where = "WHERE item_key = {item:UUID} AND transaction_key = {transaction:UUID} AND included "
    scope = {"item": str(rule.item), "transaction": str(rule.transaction)}
    if not await dashboard_query(
        f"SELECT transaction_key FROM analytics.spending_dashboard {where}FORMAT JSONEachRow",
        **scope,
    ):
        raise HTTPException(404, "Expense is unavailable")
    await dashboard_query(
        "INSERT INTO core.spending_rules (item_key, merchant_key, category) "
        "SELECT item_key, merchant_key, {category:String} "
        f"FROM analytics.spending_dashboard {where}",
        category=rule.category,
        **scope,
    )
    return Response(status_code=204)


@router.post("/reviews", status_code=204, dependencies=[Depends(same_origin)])
async def save_review(review: Review) -> Response:
    where = "WHERE item_key = {item:UUID} AND transaction_key = {transaction:UUID} AND reviewable "
    scope = {"item": str(review.item), "transaction": str(review.transaction)}
    if not await dashboard_query(
        f"SELECT transaction_key FROM analytics.spending_dashboard {where}FORMAT JSONEachRow",
        **scope,
    ):
        raise HTTPException(404, "Transaction is unavailable for review")
    await dashboard_query(
        "INSERT INTO core.spending_reviews (item_key, transaction_key, decision) "
        "SELECT item_key, transaction_key, {decision:String} "
        f"FROM analytics.spending_dashboard {where}",
        decision=review.decision,
        **scope,
    )
    return Response(status_code=204)


@router.post("/suggestions", dependencies=[Depends(same_origin)])
async def suggest_categories(request: SuggestionRequest):
    ids = sorted(set(request.transactions))
    rows = await dashboard_query(
        "SELECT transaction_key AS id, merchant_label AS merchant "
        "FROM analytics.spending_dashboard "
        "WHERE item_key = {item:UUID} AND transaction_key IN {ids:Array(UUID)} "
        "AND included AND category = 'Uncategorized' AND notEmpty(merchant_label) "
        "ORDER BY transaction_key FORMAT JSONEachRow",
        item=str(request.item),
        ids="[" + ",".join(f"'{value}'" for value in ids) + "]",
    )
    async with httpx.AsyncClient(timeout=MODEL_TIMEOUT, trust_env=False) as client:
        try:
            async with asyncio.timeout(54):
                categories = await classifier.suggest(client, [row["merchant"] for row in rows])
        except (ClassifierUnavailable, TimeoutError):
            raise HTTPException(503, "Local category suggestions are unavailable") from None
    return {
        "suggestions": [
            {"id": row["id"], "category": category}
            for row, category in zip(rows, categories, strict=True)
            if category is not None
        ]
    }
