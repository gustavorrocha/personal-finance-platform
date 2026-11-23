"""Invested money per investment class over time, valued day by day.

Each position (savings boxes included) has a class: the one the operator chose, or else an
automatic one from its type and indexer. A day with a stored balance uses it, gross of the
income tax and IOF withheld on redemption; investment balances count for the day before
they were observed, as providers report the previous close. Other days walk from the
nearest stored balance through the purchases and sales reported in between and, for
positions that follow a curve, the daily yield of that curve:

- CDI and Selic: the Banco Central daily rate times the contracted percentage, on business
  days (savings boxes included);
- fixed rate (CDB, LCA, LCI, not Treasury): (1 + annual rate) ** (1 / 252) per business day.

Positions with market prices follow the price from day to day instead: Tesouro Direto bonds
the morning redemption price published by the Tesouro, funds the quota in the CVM daily
report, stocks and ETFs the B3 closing price (dividends arrive as account transactions, not
in the position). Positions without either walk back through reported flows only, so those
days show money put in rather than market value.
"""

import re
from bisect import bisect_right
from datetime import date, timedelta
from decimal import Decimal

INFLATION = "0aa43018-e7bd-5a63-99ba-c9b0c13ca31e"
CDI = "443ce26b-6361-545f-9c5c-f7482f64d806"
PREFIXED = "389552c8-5aaf-5acb-896a-29675e75711e"
FUNDS = "f79ee425-a7d3-5738-8f2b-f247971ca8e5"
ETF_STOCKS = "9c05e606-3497-536c-9480-5b3caa66d5ce"

DAY = timedelta(days=1)


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
    return min(following - DAY, today)


def number(value) -> Decimal | None:
    return Decimal(value) if value not in (None, "") else None


def asset_key(position: dict) -> str | None:
    """Key of the position's market prices: a Tesouro Direto bond's title and due date, a
    fund's CNPJ digits or a listed asset's ticker."""
    title = re.match(r"(Tesouro .+?) \d{4}\b", position.get("name") or "")
    if position.get("subtype") == "TREASURY" and title and position.get("due_date"):
        return f"{title[1]}|{position['due_date']}"
    symbol = position.get("symbol") or ""
    digits = re.sub(r"\D", "", symbol)
    if position.get("type") == "MUTUAL_FUND" and len(digits) == 14:
        return digits
    if position.get("type") in {"EQUITY", "ETF"} and re.fullmatch(r"[A-Za-z0-9]{4,12}", symbol):
        return symbol.upper()
    return None


def price_yield(prices: dict[date, Decimal]):
    """Fraction gained from a day to the next one, at the last price on or before each."""
    days = sorted(prices)

    def price(day: date) -> Decimal | None:
        index = bisect_right(days, day)
        return prices[days[index - 1]] if index else None

    def grow(day: date) -> Decimal:
        today, following = price(day), price(day + DAY)
        return following / today - 1 if today and following else Decimal(0)

    return grow


def daily_yield(
    position: dict,
    rates: dict[str, dict[date, Decimal]],
    prices: dict[date, Decimal] | None = None,
):
    """Function of a day returning the fraction the position earns over that day."""
    if prices:
        return price_yield(prices)
    indexer = (position.get("indexer") or "").upper()
    cdi = rates.get("CDI", {})
    last = max(cdi, default=None)

    def business(day: date) -> bool:
        # Banco Central publishes rates on business days only; later days are weekdays.
        return day in cdi if last and day <= last else day.weekday() < 5

    if indexer in {"CDI", "SELIC"}:
        series = rates.get(indexer, {})
        newest = max(series, default=None)
        share = number(position.get("rate")) or Decimal(100)
        return lambda day: (
            series.get(day, series[newest] if newest and day > newest else 0) * share / 10000
            if business(day)
            else Decimal(0)
        )
    fixed = number(position.get("fixed_rate"))
    if (
        not indexer
        and fixed
        and position.get("type") == "FIXED_INCOME"
        and position.get("subtype") != "TREASURY"
    ):
        step = Decimal((1 + float(fixed) / 100) ** (1 / 252) - 1)
        return lambda day: step if business(day) else Decimal(0)
    return lambda day: Decimal(0)


def daily_values(
    rows: list[dict],
    own: list[tuple[date, Decimal]],
    start: date,
    rates: dict,
    prices: dict[date, Decimal] | None = None,
) -> tuple[dict[date, Decimal], Decimal]:
    """Value of one position at the end of each day from `start`, and its lowest walk.

    V(d) = V(d - 1) * (1 + yield(d - 1)) + flow(d); walking back inverts it. Values may be
    negative here (unreported withdrawals); callers clamp them.
    """
    latest = rows[-1]
    grow = daily_yield(latest, rates, prices)
    box = latest["type"] == "SAVINGS_BOX"
    # Investment balances arrive with the previous day's close; savings boxes are live.
    lag = timedelta(0) if box else DAY
    anchors = {
        date.fromisoformat(row["observed_on"]) - lag: Decimal(row.get("gross") or row["balance"])
        for row in rows
    }
    flow: dict[date, Decimal] = {}
    for day, net in own:
        flow[day] = flow.get(day, Decimal(0)) + net
    first, last = min(anchors), max(anchors)
    opened = min(flow, default=first)
    purchased = date.fromisoformat(latest["purchase_date"]) if latest.get("purchase_date") else None
    # A box starts empty: walk back to the day before its first movement to see whether
    # more went in than it holds and returned.
    floor = min(start, opened - DAY) if box else start
    values: dict[date, Decimal] = {}
    value = anchors[last]
    day = last
    while day >= floor:
        if day in anchors:
            value = anchors[day]
        values[day] = value
        value = (value - flow.get(day, Decimal(0))) / (1 + grow(day - DAY))
        day -= DAY
    lowest = min((v for d, v in values.items() if d >= start or d == opened - DAY), default=0)
    lowest = min(lowest, Decimal(0))
    # Forward through the month of the last stored balance; later the position is gone.
    following = date(last.year + last.month // 12, last.month % 12 + 1, 1)
    value = anchors[last]
    day = last + DAY
    while day < following:
        value = value * (1 + grow(day - DAY)) + flow.get(day, Decimal(0))
        values[day] = value
        day += DAY
    for day in values:
        if (purchased and day < purchased) or (box and day < opened) or day >= following:
            values[day] = Decimal(0)
    return values, lowest


def invested_history(
    history: list[dict],
    flows: list[dict],
    assigned: dict[str, str],
    classes: list[dict],
    month: str,
    rates: list[dict] | None = None,
    prices: list[dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    """history: position, observed_on, type, subtype, indexer, rate, fixed_rate,
    purchase_date, name, currency, balance and gross (one per day).
    flows: position, date, net (purchases and contributions positive).
    rates: series (CDI, SELIC), day, value (daily percentage).
    prices: asset (see asset_key), day, price.
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
    start = date.fromisoformat(f"{months[0]}-01") - DAY
    series: dict[str, dict[date, Decimal]] = {}
    for row in rates or []:
        series.setdefault(row["series"], {})[date.fromisoformat(row["day"])] = Decimal(row["value"])
    quotes: dict[str, dict[date, Decimal]] = {}
    for row in prices or []:
        quotes.setdefault(row["asset"], {})[date.fromisoformat(row["day"])] = Decimal(row["price"])
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
        values, lowest = daily_values(
            rows, moves.get(position, []), start, series, quotes.get(asset_key(latest) or "")
        )
        for slot in months:
            end = month_end(slot, today)
            value = values.get(end, Decimal(0))
            lowest = min(lowest, value)
            group = (slot, latest["currency"], key)
            totals[group] = totals.get(group, Decimal(0)) + max(Decimal(0), value)
        if lowest <= -1:
            gaps.append(
                {
                    "name": latest["name"] or "",
                    "currency": latest["currency"],
                    "amount": str(-lowest.quantize(Decimal("0.01"))),
                }
            )
    present = {(currency, key) for (_, currency, key), total in totals.items() if total}
    rows = [
        {
            "month": slot,
            "currency": currency,
            "key": key,
            "name": names.get(key, ""),
            "total": str(total.quantize(Decimal("0.01"))),
        }
        for (slot, currency, key), total in sorted(totals.items())
        if (currency, key) in present
    ]
    return rows, gaps
