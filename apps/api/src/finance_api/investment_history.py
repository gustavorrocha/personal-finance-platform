"""Invested money per investment class over time, from the daily balances on record.

Each position (savings boxes included) has a class: the one the operator chose, or else an
automatic one from its type and indexer. A month uses the last balance stored in it; months
before the first stored balance walk back from the next one, subtracting the purchases and
adding back the sales reported in between. Past yield and market changes are not
reconstructed for those months.
"""

from datetime import date, timedelta
from decimal import Decimal

INFLATION = "0aa43018-e7bd-5a63-99ba-c9b0c13ca31e"
CDI = "443ce26b-6361-545f-9c5c-f7482f64d806"
PREFIXED = "389552c8-5aaf-5acb-896a-29675e75711e"
FUNDS = "f79ee425-a7d3-5738-8f2b-f247971ca8e5"
ETF_STOCKS = "9c05e606-3497-536c-9480-5b3caa66d5ce"


def automatic_class(position: dict) -> str | None:
    """Class from the provider's type and indexer; None when nothing fits."""
    kind = position.get("type") or ""
    indexer = (position.get("indexer") or "").upper()
    if kind == "SAVINGS_BOX" or indexer in {"CDI", "SELIC"}:
        return CDI
    if indexer in {"IPCA", "IGPM", "IGP-M", "INPC"}:
        return INFLATION
    if kind == "FIXED_INCOME":
        return PREFIXED
    if kind == "MUTUAL_FUND":
        return FUNDS
    if kind in {"EQUITY", "ETF"}:
        return ETF_STOCKS
    return None


def position_class(position: dict, assigned: dict[str, str], active: set[str]) -> str:
    """The chosen class, else the automatic one; "" when neither is an active class."""
    for candidate in (assigned.get(position["position"]), automatic_class(position)):
        if candidate in active:
            return candidate
    return ""


def month_end(slot: str, today: date) -> date:
    year, month = map(int, slot.split("-"))
    following = date(year + month // 12, month % 12 + 1, 1)
    return min(following - timedelta(days=1), today)


def invested_history(
    history: list[dict],
    flows: list[dict],
    assigned: dict[str, str],
    classes: list[dict],
    month: str,
) -> tuple[list[dict], list[dict]]:
    """history: position, observed_on, type, indexer, name, currency, balance (one per day).
    flows: position, date, net (purchases and contributions positive).
    Returns rows (month, currency, key = class id or "", name, total) for the 12 months up
    to `month`, and gaps: positions whose walk back fell below zero, such as a savings box
    that paid a bill without a reported withdrawal.
    """
    today = date.today()
    first = date.fromisoformat(f"{month}-01")
    index = first.year * 12 + first.month - 1
    months = [
        f"{(index - offset) // 12:04d}-{(index - offset) % 12 + 1:02d}"
        for offset in range(11, -1, -1)
    ]
    months = [slot for slot in months if slot <= today.strftime("%Y-%m")]
    names = {row["id"]: row["name"] for row in classes}
    snapshots: dict[str, list[dict]] = {}
    for row in sorted(history, key=lambda row: row["observed_on"]):
        snapshots.setdefault(row["position"], []).append(row)
    moves: dict[str, list[tuple[date, Decimal]]] = {}
    for row in flows:
        moves.setdefault(row["position"], []).append(
            (date.fromisoformat(row["date"]), Decimal(row["net"] or 0))
        )
    totals: dict[tuple[str, str, str], Decimal] = {}
    gaps = []
    for position, rows in snapshots.items():
        latest = rows[-1]
        key = position_class(latest, assigned, set(names))
        own = moves.get(position, [])
        opened = min((day for day, _ in own), default=date.fromisoformat(rows[0]["observed_on"]))
        lowest = Decimal(0)
        if latest["type"] == "SAVINGS_BOX":
            # A box starts empty: what went in beyond its first stored balance left it
            # without a reported withdrawal.
            since = date.fromisoformat(rows[0]["observed_on"])
            before = sum((net for day, net in own if day <= since), Decimal(0))
            lowest = min(lowest, Decimal(rows[0]["balance"]) - before)
        for slot in months:
            end = month_end(slot, today)
            inside = [row for row in rows if row["observed_on"][:7] == slot]
            later = [row for row in rows if date.fromisoformat(row["observed_on"]) > end]
            if inside and date.fromisoformat(inside[-1]["observed_on"]) <= end:
                value = Decimal(inside[-1]["balance"])
            elif later:
                anchor = later[0]
                until = date.fromisoformat(anchor["observed_on"])
                value = Decimal(anchor["balance"]) - sum(
                    (net for day, net in own if end < day <= until), Decimal(0)
                )
                # A savings box holds nothing before its first reported movement.
                if latest["type"] == "SAVINGS_BOX" and end < opened:
                    value = Decimal(0)
            else:
                # No longer reported: sold or closed.
                value = Decimal(0)
            lowest = min(lowest, value)
            group = (slot, latest["currency"], key)
            totals[group] = totals.get(group, Decimal(0)) + max(Decimal(0), value)
        if lowest <= -1:
            gaps.append(
                {
                    "name": latest["name"] or "",
                    "currency": latest["currency"],
                    "amount": str(-lowest),
                }
            )
    present = {(currency, key) for (_, currency, key), total in totals.items() if total}
    rows = [
        {
            "month": slot,
            "currency": currency,
            "key": key,
            "name": names.get(key, ""),
            "total": str(total),
        }
        for (slot, currency, key), total in sorted(totals.items())
        if (currency, key) in present
    ]
    return rows, gaps
