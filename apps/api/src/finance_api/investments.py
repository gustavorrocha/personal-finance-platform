"""Connection-scoped investment positions and their editable classes."""

from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from .accounts import SNAPSHOT_LIMIT, select_connection
from .investment_history import automatic_class, position_class
from .spending import (
    DEMO_ITEM,
    INVESTMENT_ASSIGNMENTS,
    INVESTMENT_CLASS_LIST,
    ZERO_UUID,
    add_institutions,
    dashboard_query,
    same_origin,
)

router = APIRouter()


@router.get("/api/investments")
async def investment_snapshot(item: UUID | None = None):
    connections = await dashboard_query(
        "SELECT item_key AS id FROM analytics.investments_dashboard "
        "GROUP BY item_key ORDER BY item_key FORMAT JSONEachRow"
    )
    await add_institutions(connections)
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


class ClassInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class Assignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: UUID
    # None returns the position to its automatic class.
    class_id: UUID | None


async def held_positions() -> list[dict]:
    """Latest reported balance of every position across connections, demo excluded."""
    return await dashboard_query(
        "SELECT toString(position_key) AS position, toString(item_key) AS item, type, "
        "indexer, name, symbol, currency, toString(balance) AS balance "
        "FROM analytics.investment_position_history WHERE item_key != {demo:UUID} "
        "ORDER BY observed_on DESC LIMIT 1 BY position_key FORMAT JSONEachRow",
        demo=DEMO_ITEM,
    )


@router.get("/api/investments/classes")
async def investment_classes():
    """Classes, and each currently held position with its chosen and automatic class."""
    classes = await dashboard_query(INVESTMENT_CLASS_LIST)
    assigned = {
        row["position"]: row["class"] for row in await dashboard_query(INVESTMENT_ASSIGNMENTS)
    }
    positions = await held_positions()
    active = {row["id"] for row in classes}
    return {
        "classes": classes,
        "positions": [
            {
                **row,
                "class_id": assigned.get(row["position"], ""),
                "automatic_id": automatic if (automatic := automatic_class(row)) in active else "",
            }
            for row in sorted(positions, key=lambda row: (row["type"] or "", row["name"] or ""))
            if Decimal(row["balance"]) != 0
        ],
    }


async def write_class(class_id: UUID, name: str, archived: bool) -> None:
    await dashboard_query(
        "INSERT INTO core.investment_classes (class_id, name, archived) "
        "SELECT {id:UUID}, {name:String}, {archived:Bool}",
        id=str(class_id),
        name=name,
        archived=str(archived).lower(),
    )


async def active_class(class_id: UUID) -> dict:
    rows = await dashboard_query(
        "SELECT name FROM analytics.investment_classes WHERE class_id = {id:UUID} "
        "FORMAT JSONEachRow",
        id=str(class_id),
    )
    if not rows:
        raise HTTPException(404, "Unknown investment class")
    return rows[0]


@router.post("/api/investments/classes", status_code=201, dependencies=[Depends(same_origin)])
async def create_class(body: ClassInput):
    identifier = uuid4()
    await write_class(identifier, body.name, False)
    return {"id": str(identifier)}


@router.put(
    "/api/investments/classes/{class_id}", status_code=204, dependencies=[Depends(same_origin)]
)
async def rename_class(class_id: UUID, body: ClassInput) -> Response:
    await active_class(class_id)
    await write_class(class_id, body.name, False)
    return Response(status_code=204)


@router.delete(
    "/api/investments/classes/{class_id}", status_code=204, dependencies=[Depends(same_origin)]
)
async def delete_class(class_id: UUID) -> Response:
    """Positions in a deleted class return to their automatic class, if it is active."""
    current = await active_class(class_id)
    await write_class(class_id, current["name"], True)
    return Response(status_code=204)


@router.post("/api/investments/assignments", status_code=204, dependencies=[Depends(same_origin)])
async def assign_class(body: Assignment) -> Response:
    if body.class_id is not None:
        await active_class(body.class_id)
    await dashboard_query(
        "INSERT INTO core.investment_class_assignments (position_key, class_id) "
        "SELECT {position:UUID}, {id:UUID}",
        position=str(body.position),
        id=str(body.class_id or ZERO_UUID),
    )
    return Response(status_code=204)


TARGET_LIST = (
    "SELECT toString(class_id) AS id, toString(percent) AS percent "
    "FROM analytics.investment_class_targets FORMAT JSONEachRow"
)


@router.get("/api/investments/allocation")
async def allocation():
    """Targets, money held per class and currency, and bank balances available to invest."""
    classes = await dashboard_query(INVESTMENT_CLASS_LIST)
    targets = {row["id"]: row["percent"] for row in await dashboard_query(TARGET_LIST)}
    assigned = {
        row["position"]: row["class"] for row in await dashboard_query(INVESTMENT_ASSIGNMENTS)
    }
    active = {row["id"] for row in classes}
    held: dict[tuple[str, str], Decimal] = {}
    for row in await held_positions():
        key = (row["currency"], position_class(row, assigned, active))
        held[key] = held.get(key, Decimal(0)) + Decimal(row["balance"])
    cash = await dashboard_query(
        "SELECT currency, toString(sum(balance)) AS total FROM analytics.accounts_dashboard "
        "WHERE item_key != {demo:UUID} AND NOT disabled AND balance IS NOT NULL "
        "AND account_type = 'BANK' GROUP BY currency ORDER BY currency FORMAT JSONEachRow",
        demo=DEMO_ITEM,
    )
    return {
        "classes": [{**row, "target": targets.get(row["id"], "0")} for row in classes],
        "held": [
            {"currency": currency, "class_id": key, "total": str(total)}
            for (currency, key), total in sorted(held.items())
            if total != 0
        ],
        "cash": cash,
    }


Percent = Annotated[Decimal, Field(ge=0, le=100, decimal_places=4)]


class Targets(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Every active class not listed loses its target.
    targets: dict[UUID, Percent]


@router.put("/api/investments/targets", status_code=204, dependencies=[Depends(same_origin)])
async def save_targets(body: Targets) -> Response:
    total = sum(body.targets.values(), Decimal(0))
    if total not in (0, 100):
        raise HTTPException(422, "Targets must add up to 100%")
    active = {row["id"] for row in await dashboard_query(INVESTMENT_CLASS_LIST)}
    if any(str(key) not in active for key in body.targets):
        raise HTTPException(404, "Unknown investment class")
    # Write only changes, so the history shows what the operator actually edited.
    current = {row["id"]: Decimal(row["percent"]) for row in await dashboard_query(TARGET_LIST)}
    changes = {
        key: percent
        for key in sorted(active)
        if (percent := body.targets.get(UUID(key), Decimal(0))) != current.get(key, Decimal(0))
    }
    if changes:
        # Both arrays hold validated UUIDs and decimals only.
        await dashboard_query(
            "INSERT INTO core.investment_class_targets (class_id, percent) "
            "SELECT tupleElement(pair, 1), tupleElement(pair, 2) FROM "
            "(SELECT arrayJoin(arrayZip({ids:Array(UUID)}, {percents:Array(Decimal(7, 4))})) "
            "AS pair)",
            ids="[" + ",".join(f"'{key}'" for key in changes) + "]",
            percents="[" + ",".join(str(value) for value in changes.values()) + "]",
        )
    return Response(status_code=204)
