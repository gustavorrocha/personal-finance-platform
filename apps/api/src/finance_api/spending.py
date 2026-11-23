"""Same-origin dashboard access to a narrow ClickHouse projection."""

import asyncio
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from .investment_history import invested_history
from .local_classifier import (
    BATCH_LIMIT,
    MODEL_TIMEOUT,
    ClassifierUnavailable,
    LocalClassifier,
)
from .savings_inference import suggest as suggest_box_payments

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
    "mcc, cnpj, cnae, business_name, merchant_category, "
    "subcategory, category_id, category_rule "
)
ZERO_UUID = "00000000-0000-0000-0000-000000000000"
CATEGORY_LIST = (
    "SELECT toString(category_id) AS id, "
    f"if(parent_id = toUUID('{ZERO_UUID}'), NULL, toString(parent_id)) AS parent_id, name "
    "FROM analytics.spending_categories ORDER BY name FORMAT JSONEachRow"
)
INVESTMENT_CLASS_LIST = (
    "SELECT toString(class_id) AS id, name FROM analytics.investment_classes "
    "ORDER BY name FORMAT JSONEachRow"
)
INVESTMENT_ASSIGNMENTS = (
    "SELECT toString(position_key) AS position, toString(class_id) AS class "
    "FROM analytics.investment_class_assignments FORMAT JSONEachRow"
)
# Where a category correction applies: one merchant, one card MCC or one provider category.
RULE_KEYS = {
    "transaction": "concat(toString(item_key), ':', toString(transaction_key))",
    "merchant": "merchant_key",
    "mcc": "ifNull(toString(mcc), '')",
    "provider": "provider_category_id",
}


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item: UUID
    transaction: UUID
    scope: Literal["transaction", "merchant", "mcc", "provider"] = "merchant"
    # None clears the rule so the transaction falls back to automatic classification.
    category: UUID | None


Month = Annotated[str, StringConstraints(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]


class ManualExpense(BaseModel):
    """A one-off (end = start) or recurring expense the provider does not report."""

    model_config = ConfigDict(extra="forbid")

    item: UUID
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
    ]
    amount: Annotated[Decimal, Field(gt=0, lt=Decimal("1e9"), decimal_places=2)]
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")] = "BRL"
    category: UUID | None = None
    day: Annotated[int, Field(ge=1, le=31)]
    start: Month
    end: Month | None = None
    cnpj: Annotated[str, StringConstraints(pattern=r"^(\d{14})?$")] = ""
    # The savings box that paid it: each occurrence counts as a withdrawal from that box.
    savings_box: Annotated[str, StringConstraints(strip_whitespace=True, max_length=512)] = ""


class CategoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
    parent: UUID | None = None


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
    # Exact category and subcategory of the listed expenses; "" means none.
    category: Annotated[str | None, Query(max_length=60)] = None,
    subcategory: Annotated[str | None, Query(max_length=60)] = None,
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
        "invested_history": [],
        "invested_gaps": [],
        "chart_month": None,
        "expenses": [],
        "has_more_expenses": False,
        "reviews": [],
        "receipts": [],
        "categories": await dashboard_query(CATEGORY_LIST),
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
    # Charts keep a fixed 12-month axis ending at the latest month with data; only a
    # month older than that axis moves it.
    latest = date.fromisoformat(f"{max(month, selected['latest_month'])}-01")
    end = latest.year * 12 + latest.month - 1
    if months <= end - HISTORY_MONTHS + 1:
        end = months
    result["chart_month"] = month_start(end).strftime("%Y-%m")
    window = filters | {
        # The month before the selected one is always needed for comparisons.
        "since": max(
            month_start(min(months - 1, end - HISTORY_MONTHS + 1)), date(1970, 1, 1)
        ).isoformat(),
        "until": month_start(end + 1).isoformat(),
    }
    in_window = (
        f"WHERE {scope} AND economic_date >= {{since:Date}} AND economic_date < {{until:Date}} "
    )
    result["history"] = await dashboard_query(
        "SELECT formatDateTime(toStartOfMonth(economic_date), '%Y-%m') AS month, currency, "
        "source, status, category, subcategory, toString(sum(amount)) AS total, "
        "count() AS entries "
        "FROM (SELECT item_key, economic_date, currency, source, category, subcategory, "
        "toDecimal128(net_amount, 12) AS amount, 'POSTED' AS status "
        "FROM analytics.spending_dashboard WHERE included "
        "UNION ALL SELECT item_key, economic_date, currency, 'card' AS source, category, "
        "subcategory, "
        "toDecimal128(amount, 12) AS amount, 'PENDING' AS status "
        "FROM analytics.pending_card_spending) "
        f"{in_window}GROUP BY month, currency, source, status, category, subcategory "
        "ORDER BY month, currency, source, status, category, subcategory FORMAT JSONEachRow",
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
    positions = await dashboard_query(
        "SELECT toString(position_key) AS position, toString(observed_on) AS observed_on, "
        "type, indexer, name, currency, toString(balance) AS balance "
        f"FROM analytics.investment_position_history WHERE {scope} FORMAT JSONEachRow",
        **filters,
    )
    # Purchases and sales per position; contributions and withdrawals per savings box.
    flows = await dashboard_query(
        "SELECT toString(position_key) AS position, toString(economic_date) AS date, "
        "toString(sum(if(type = 'BUY', amount, -amount))) AS net "
        f"FROM analytics.investment_position_movements WHERE {scope} "
        "GROUP BY position, date UNION ALL "
        "SELECT toString(b.box_key), toString(f.economic_date), "
        "toString(sum(if(f.kind = 'contribution', f.amount, -f.amount))) "
        "FROM (SELECT * FROM analytics.investment_flows WHERE "
        f"{scope} AND savings_box != '' AND kind IN ('contribution', 'withdrawal')) AS f "
        "INNER JOIN (SELECT DISTINCT item_key, box_key, lower(name) AS box "
        "FROM analytics.savings_box_history) AS b "
        "ON f.item_key = b.item_key AND lower(f.savings_box) = b.box "
        "GROUP BY b.box_key, f.economic_date FORMAT JSONEachRow",
        **filters,
    )
    classes = await dashboard_query(INVESTMENT_CLASS_LIST)
    assigned = await dashboard_query(INVESTMENT_ASSIGNMENTS)
    result["invested_history"], result["invested_gaps"] = invested_history(
        positions,
        flows,
        {row["position"]: row["class"] for row in assigned},
        classes,
        result["chart_month"],
    )
    search = search.strip()
    expense_filters = dict(filters, offset=str((page - 1) * EXPENSE_PAGE_SIZE))
    conditions = []
    if search:
        expense_filters["search"] = search
        conditions.append(
            "(positionCaseInsensitiveUTF8(description, {search:String}) > 0 "
            "OR positionCaseInsensitiveUTF8(merchant, {search:String}) > 0 "
            "OR positionCaseInsensitiveUTF8(category, {search:String}) > 0 "
            "OR positionCaseInsensitiveUTF8(subcategory, {search:String}) > 0 "
            "OR positionCaseInsensitiveUTF8(bank_category, {search:String}) > 0)"
        )
    for name, value in (("category", category), ("subcategory", subcategory)):
        if value is not None:
            expense_filters[name] = value
            conditions.append(f"{name} = {{{name}:String}}")
    search_filter = f"WHERE {' AND '.join(conditions)} " if conditions else ""
    details = (
        "item_key AS item, transaction_key AS id, economic_date AS date, currency, "
        "merchant_label AS merchant, category, " + TRANSACTION_DETAILS
    )
    expenses = await dashboard_query(
        f"SELECT * FROM (SELECT {details}, toString(net_amount) AS amount, "
        "provider_category_id, operation, "
        f"'POSTED' AS status FROM analytics.spending_dashboard {where}AND included "
        f"UNION ALL SELECT {details}, toString(amount) AS amount, provider_category_id, "
        "'' AS operation, "
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
        # The review is a backlog: pending debits from every month, then recent decisions.
        f"FROM analytics.spending_dashboard WHERE {scope} AND reviewable "
        "ORDER BY (decision != ''), date DESC, transaction_key DESC LIMIT 100 FORMAT JSONEachRow",
        **filters,
    )
    # Transfers received this month that may refund part of an expense.
    result["receipts"] = await dashboard_query(
        "SELECT item_key AS item, transaction_key AS id, economic_date AS date, currency, "
        "toString(abs(net_amount)) AS amount, merchant_label AS merchant, operation, decision, "
        "category, provider_category_id, "
        f"{TRANSACTION_DETAILS}"
        f"FROM analytics.spending_dashboard {where}AND reimbursable "
        "ORDER BY (decision != ''), date DESC, transaction_key DESC LIMIT 100 FORMAT JSONEachRow",
        **filters,
    )
    return result


def same_origin(request: Request) -> None:
    if request.headers.get("origin") not in ORIGINS:
        raise HTTPException(403, "Open the local dashboard to change a category")
    if request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
        raise HTTPException(415, "Expected JSON")


async def active_category(category: UUID) -> dict:
    rows = await dashboard_query(
        "SELECT toString(parent_id) AS parent_id, name FROM analytics.spending_categories "
        "WHERE category_id = {category:UUID} FORMAT JSONEachRow",
        category=str(category),
    )
    if not rows:
        raise HTTPException(404, "Category is unavailable")
    return rows[0]


@router.post("/rules", status_code=204, dependencies=[Depends(same_origin)])
async def save_rule(rule: Rule) -> Response:
    scope = {"item": str(rule.item), "transaction": str(rule.transaction)}
    # Counted expenses, including card purchases still pending: they are already in the month.
    columns = "item_key, transaction_key, merchant_key, mcc, provider_category_id"
    rows = await dashboard_query(
        f"SELECT {RULE_KEYS[rule.scope]} AS rule_key FROM ("
        f"SELECT {columns} FROM analytics.spending_dashboard WHERE included "
        f"UNION ALL SELECT {columns} FROM analytics.pending_card_spending) "
        "WHERE item_key = {item:UUID} AND transaction_key = {transaction:UUID} "
        "LIMIT 1 FORMAT JSONEachRow",
        **scope,
    )
    if not rows:
        raise HTTPException(404, "Expense is unavailable")
    if not rows[0]["rule_key"]:
        raise HTTPException(409, "The expense has no value for this rule")
    if rule.category is not None:
        await active_category(rule.category)
    await dashboard_query(
        "INSERT INTO core.category_rules (scope, rule_key, category_id) "
        "SELECT {scope:String}, {key:String}, {category:UUID}",
        scope=rule.scope,
        key=rows[0]["rule_key"],
        category=str(rule.category or ZERO_UUID),
    )
    await reload_rules()
    return Response(status_code=204)


MANUAL_LIST = (
    "SELECT toString(entry_id) AS id, toString(item_key) AS item, description, "
    "toString(amount) AS amount, currency, "
    f"if(category_id = toUUID('{ZERO_UUID}'), NULL, toString(category_id)) AS category, "
    "day_of_month AS day, formatDateTime(start_month, '%Y-%m') AS start, "
    "if(end_month IS NULL, NULL, formatDateTime(end_month, '%Y-%m')) AS end, cnpj, "
    "savings_box "
    "FROM analytics.manual_expenses ORDER BY description, start FORMAT JSONEachRow"
)


@router.get("/manual")
async def list_manual_expenses():
    return {
        "entries": await dashboard_query(MANUAL_LIST),
        "boxes": await dashboard_query(
            "SELECT toString(item_key) AS item, name FROM analytics.savings_boxes "
            "ORDER BY name FORMAT JSONEachRow"
        ),
    }


async def write_manual(entry: UUID, expense: ManualExpense, archived: bool = False) -> None:
    if expense.end is not None and expense.end < expense.start:
        raise HTTPException(422, "Invalid request")
    # Archiving keeps the stored values even if their category was archived meanwhile.
    if not archived:
        connections = await dashboard_query(
            "SELECT item_key FROM analytics.provider_spending WHERE item_key = {item:UUID} "
            "AND item_key != {demo:UUID} LIMIT 1 FORMAT JSONEachRow",
            item=str(expense.item),
            demo=DEMO_ITEM,
        )
        if not connections:
            raise HTTPException(404, "Connection has no reported expenses")
        if expense.category is not None:
            await active_category(expense.category)
        if expense.savings_box and not await dashboard_query(
            "SELECT name FROM analytics.savings_boxes WHERE item_key = {item:UUID} "
            "AND name = {box:String} LIMIT 1 FORMAT JSONEachRow",
            item=str(expense.item),
            box=expense.savings_box,
        ):
            raise HTTPException(404, "Savings box is unavailable")
    await dashboard_query(
        "INSERT INTO core.manual_expenses (entry_id, item_key, description, amount, currency, "
        "category_id, day_of_month, start_month, end_month, cnpj, savings_box, archived) "
        "SELECT {entry:UUID}, {item:UUID}, {description:String}, {amount:Decimal(38, 12)}, "
        "{currency:String}, {category:UUID}, {day:UInt8}, {start:Date}, "
        "if({end:String} = '', NULL, toDate({end:String})), {cnpj:String}, {box:String}, "
        "{archived:Bool}",
        entry=str(entry),
        item=str(expense.item),
        description=expense.description,
        amount=str(expense.amount),
        currency=expense.currency,
        category=str(expense.category or ZERO_UUID),
        day=str(expense.day),
        start=f"{expense.start}-01",
        end=f"{expense.end}-01" if expense.end else "",
        cnpj=expense.cnpj,
        box=expense.savings_box,
        archived=str(archived).lower(),
    )


@router.post("/manual", status_code=201, dependencies=[Depends(same_origin)])
async def create_manual_expense(expense: ManualExpense):
    entry = uuid4()
    await write_manual(entry, expense)
    return {"id": str(entry)}


async def current_manual(entry: UUID) -> dict:
    rows = [row for row in await dashboard_query(MANUAL_LIST) if row["id"] == str(entry)]
    if not rows:
        raise HTTPException(404, "Entry is unavailable")
    return rows[0]


@router.put("/manual/{entry}", status_code=204, dependencies=[Depends(same_origin)])
async def update_manual_expense(entry: UUID, expense: ManualExpense) -> Response:
    await current_manual(entry)
    await write_manual(entry, expense)
    return Response(status_code=204)


@router.delete("/manual/{entry}", status_code=204, dependencies=[Depends(same_origin)])
async def archive_manual_expense(entry: UUID) -> Response:
    row = await current_manual(entry)
    expense = ManualExpense(
        item=row["item"],
        description=row["description"],
        amount=Decimal(row["amount"]).quantize(Decimal("0.01")),
        currency=row["currency"],
        category=row["category"],
        day=row["day"],
        start=row["start"],
        end=row["end"],
        cnpj=row["cnpj"],
        savings_box=row["savings_box"],
    )
    await write_manual(entry, expense, archived=True)
    return Response(status_code=204)


class Dismissal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cnpj: Annotated[str, StringConstraints(pattern=r"^\d{14}$")]
    month: Month


@router.get("/savings-box-suggestions")
async def savings_box_suggestions():
    """Monthly bills that were likely paid straight from a savings box."""
    boxes = await dashboard_query(
        "SELECT toString(b.item_key) AS item, b.name AS name, toString(b.balance) AS balance, "
        "toString(b.indexer_percentage) AS pct, toString(h.since) AS observed_since "
        "FROM analytics.savings_boxes AS b LEFT JOIN (SELECT box_key, min(observed_on) AS since "
        "FROM analytics.savings_box_history GROUP BY box_key) AS h ON b.box_key = h.box_key "
        "WHERE b.item_key != {demo:UUID} FORMAT JSONEachRow",
        demo=DEMO_ITEM,
    )
    outflows = await dashboard_query(
        "SELECT toString(item_key) AS item, name AS box, toString(previous_day) AS start, "
        "toString(economic_date) AS end, toString(amount) AS amount, "
        "toString(previous_balance) AS previous_balance "
        "FROM analytics.savings_box_outflows WHERE item_key != {demo:UUID} FORMAT JSONEachRow",
        demo=DEMO_ITEM,
    )
    flows = await dashboard_query(
        "SELECT toString(item_key) AS item, lower(savings_box) AS box, "
        "toString(economic_date) AS date, kind, toString(amount) AS amount "
        "FROM analytics.investment_flows WHERE savings_box != '' "
        "AND kind IN ('contribution', 'withdrawal') AND item_key != {demo:UUID} "
        "FORMAT JSONEachRow",
        demo=DEMO_ITEM,
    )
    payments = await dashboard_query(
        "SELECT toString(item_key) AS item, toString(economic_date) AS date, "
        "toString(net_amount) AS amount, cnpj, "
        "if(business_name != '', business_name, merchant_label) AS payee, category_id, "
        "if(subcategory != '', concat(category, ' › ', subcategory), category) AS category "
        "FROM analytics.spending_dashboard WHERE included AND net_amount > 0 AND cnpj != '' "
        "AND item_key != {demo:UUID} FORMAT JSONEachRow",
        demo=DEMO_ITEM,
    )
    dismissed = await dashboard_query(
        "SELECT cnpj, month FROM analytics.inferred_payment_dismissals FORMAT JSONEachRow"
    )
    return suggest_box_payments(
        boxes,
        flows,
        payments,
        {(row["cnpj"], row["month"]) for row in dismissed},
        date.today(),
        outflows,
    )


@router.post(
    "/savings-box-suggestions/dismiss", status_code=204, dependencies=[Depends(same_origin)]
)
async def dismiss_box_payment(dismissal: Dismissal) -> Response:
    await dashboard_query(
        "INSERT INTO core.inferred_payment_dismissals (cnpj, month) "
        "SELECT {cnpj:String}, {month:Date}",
        cnpj=dismissal.cnpj,
        month=f"{dismissal.month}-01",
    )
    return Response(status_code=204)


@router.get("/categories")
async def list_categories():
    return {"categories": await dashboard_query(CATEGORY_LIST)}


async def category_parent(category: CategoryInput, moving: UUID | None = None) -> str:
    """Subcategories sit directly under an active top-level category: two levels at most."""
    if category.parent is None:
        return ZERO_UUID
    if category.parent == moving:
        raise HTTPException(409, "A category cannot contain itself")
    if (await active_category(category.parent))["parent_id"] != ZERO_UUID:
        raise HTTPException(409, "A subcategory must belong to a top-level category")
    return str(category.parent)


async def write_category(category: UUID, parent: str, name: str, archived: bool) -> None:
    await dashboard_query(
        "INSERT INTO core.spending_categories (category_id, parent_id, name, archived) "
        "SELECT {category:UUID}, {parent:UUID}, {name:String}, {archived:Bool}",
        category=str(category),
        parent=parent,
        name=name,
        archived=str(archived).lower(),
    )
    await reload_rules()


async def reload_rules() -> None:
    """Spending views read rules from an in-memory dictionary; refresh it after a change."""
    await dashboard_query("SYSTEM RELOAD DICTIONARY core.category_rule_dict")


@router.post("/categories", status_code=201, dependencies=[Depends(same_origin)])
async def create_category(category: CategoryInput):
    identifier = uuid4()
    await write_category(identifier, await category_parent(category), category.name, False)
    return {"id": str(identifier)}


@router.put("/categories/{category_id}", status_code=204, dependencies=[Depends(same_origin)])
async def update_category(category_id: UUID, category: CategoryInput) -> Response:
    current = await active_category(category_id)
    parent = await category_parent(category, moving=category_id)
    if current["parent_id"] == ZERO_UUID and parent != ZERO_UUID:
        children = await dashboard_query(
            "SELECT category_id FROM analytics.spending_categories "
            "WHERE parent_id = {category:UUID} LIMIT 1 FORMAT JSONEachRow",
            category=str(category_id),
        )
        if children:
            raise HTTPException(409, "Move or archive its subcategories first")
    await write_category(category_id, parent, category.name, False)
    return Response(status_code=204)


@router.delete("/categories/{category_id}", status_code=204, dependencies=[Depends(same_origin)])
async def archive_category(category_id: UUID) -> Response:
    current = await active_category(category_id)
    await write_category(category_id, current["parent_id"], current["name"], True)
    return Response(status_code=204)


@router.post("/reviews", status_code=204, dependencies=[Depends(same_origin)])
async def save_review(review: Review) -> Response:
    where = (
        "WHERE item_key = {item:UUID} AND transaction_key = {transaction:UUID} "
        "AND (reviewable OR reimbursable) "
    )
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
        "AND included AND category = '' AND notEmpty(merchant_label) "
        "ORDER BY transaction_key FORMAT JSONEachRow",
        item=str(request.item),
        ids="[" + ",".join(f"'{value}'" for value in ids) + "]",
    )
    tree = await dashboard_query(CATEGORY_LIST)
    names = {row["id"]: row["name"] for row in tree}
    labels = {
        f"{names[row['parent_id']]} / {row['name']}" if row["parent_id"] else row["name"]: row["id"]
        for row in tree
        if not row["parent_id"] or row["parent_id"] in names
    }
    async with httpx.AsyncClient(timeout=MODEL_TIMEOUT, trust_env=False) as client:
        try:
            async with asyncio.timeout(54):
                categories = await classifier.suggest(
                    client, [row["merchant"] for row in rows], sorted(labels)
                )
        except (ClassifierUnavailable, TimeoutError):
            raise HTTPException(503, "Local category suggestions are unavailable") from None
    return {
        "suggestions": [
            {"id": row["id"], "category": labels[category], "label": category}
            for row, category in zip(rows, categories, strict=True)
            if category is not None
        ]
    }
