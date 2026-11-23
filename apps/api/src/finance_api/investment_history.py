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


def coupon_days(position: dict) -> set[date]:
    """Payment dates of a Tesouro bond with semiannual interest: the due date's day, in
    its month and six months apart."""
    due = position.get("due_date")
    if "Juros Semestrais" not in (position.get("name") or "") or not due:
        return set()
    due = date.fromisoformat(due)
    return {
        date(year, month, due.day)
        for year in range(due.year - 40, due.year + 1)
        for month in {due.month, (due.month + 5) % 12 + 1}
    }


def price_yield(prices: dict[date, Decimal], coupons: set[date] = frozenset()):
    """Fraction gained from a day to the next one, at the last price on or before each.

    A step across a coupon payment counts as zero: the price drops by the coupon, which is
    paid out to the account rather than lost.
    """
    days = sorted(prices)

    def quote(day: date) -> tuple[date, Decimal] | None:
        index = bisect_right(days, day)
        return (days[index - 1], prices[days[index - 1]]) if index else None

    def grow(day: date) -> Decimal:
        today, following = quote(day), quote(day + DAY)
        if not today or not following or today[0] == following[0]:
            return Decimal(0)
        if any(today[0] < coupon <= following[0] for coupon in coupons):
            return Decimal(0)
        return following[1] / today[1] - 1

    return grow


def daily_yield(
    position: dict,
    rates: dict[str, dict[date, Decimal]],
    prices: dict[date, Decimal] | None = None,
    income: bool = False,
):
    """Function of a day returning the fraction the position earns over that day; None
    when the position follows neither a rate nor a market price. With `income`, coupons
    paid out count as earned (for returns); without, the value drops by them."""
    if prices:
        return price_yield(prices, coupon_days(position) if income else frozenset())
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
    return None


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
    grow = daily_yield(latest, rates, prices) or (lambda day: Decimal(0))
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


def prepare(history, flows, classes, rates, prices):
    """Rates per series, prices per asset, class names, snapshots and flows per position."""
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
    return series, quotes, names, snapshots, moves


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
    series, quotes, names, snapshots, moves = prepare(history, flows, classes, rates, prices)
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


PERIODS = ("month", "3m", "6m", "12m", "ytd")
CENTS = Decimal("0.01")


def months_before(day: date, count: int) -> date:
    index = day.year * 12 + day.month - 1 - count
    year, month = index // 12, index % 12 + 1
    last = (date(year + month // 12, month % 12 + 1, 1) - DAY).day
    return date(year, month, min(day.day, last))


def invested_returns(
    history: list[dict],
    flows: list[dict],
    assigned: dict[str, str],
    classes: list[dict],
    rates: list[dict] | None = None,
    prices: list[dict] | None = None,
) -> dict:
    """Time-weighted returns, gross of income tax, of the portfolio, each class and each
    held position (BRL), up to yesterday, against the CDI.

    A position's daily return is its model's (rate curve or market price), so purchases,
    sales and payments made straight from a savings box are not gains or losses; a group's
    is the average of its positions weighted by the previous day's value. Positions without
    a model are left out and listed as uncovered.
    """
    end = date.today() - DAY
    bases = {
        "month": date(end.year, end.month, 1) - DAY,
        "3m": months_before(end, 3),
        "6m": months_before(end, 6),
        "12m": months_before(end, 12),
        "ytd": date(end.year, 1, 1) - DAY,
    }
    start = min(bases.values())
    days = [start + DAY * offset for offset in range((end - start).days + 1)]
    series, quotes, names, snapshots, moves = prepare(history, flows, classes, rates, prices)
    active = set(names)
    weight: dict[str, list[Decimal]] = {}
    earned: dict[str, list[Decimal]] = {}
    held: dict[str, Decimal] = {}
    members: dict[str, list[dict]] = {}
    uncovered = []
    for position, rows in snapshots.items():
        latest = rows[-1]
        if latest["currency"] != "BRL":
            continue
        own_prices = quotes.get(asset_key(latest) or "")
        grow = daily_yield(latest, series, own_prices, income=True)
        values, _ = daily_values(rows, moves.get(position, []), start, series, own_prices)
        value = max(Decimal(0), values.get(end, Decimal(0)))
        name = latest["name"] or latest.get("symbol") or ""
        if grow is None:
            if value:
                uncovered.append({"name": name, "value": str(value.quantize(CENTS))})
            continue
        key = position_class(latest, assigned, active)
        for group in ("", key):
            held[group] = held.get(group, Decimal(0)) + value
        for offset, day in enumerate(days[1:], start=1):
            previous = max(Decimal(0), values.get(day - DAY, Decimal(0)))
            if previous:
                gain = previous * grow(day - DAY)
                for group in ("", f"class:{key}", position):
                    weight.setdefault(group, [Decimal(0)] * len(days))[offset] += previous
                    earned.setdefault(group, [Decimal(0)] * len(days))[offset] += gain
        members.setdefault(key, [])
        if value:
            members[key].append({"key": position, "name": name, "value": value})

    cdi_yield = daily_yield({"indexer": "CDI", "rate": "100"}, series)
    cdi_daily = [Decimal(0)] + [cdi_yield(day - DAY) for day in days[1:]]
    nothing = [Decimal(0)] * len(days)

    def compound(daily: list[Decimal]) -> list[Decimal]:
        level, result = Decimal(1), [Decimal(1)]
        for value in daily[1:]:
            level *= 1 + value
            result.append(level)
        return result

    def measure(group: str) -> tuple[list[Decimal], list[Decimal], list[Decimal]]:
        """Levels of the group and of the CDI over the days the group was held, and its
        daily weights."""
        weights = weight.get(group, nothing)
        own = [
            earned[group][o] / weights[o] if weights[o] else Decimal(0) for o in range(len(days))
        ]
        benchmark = [cdi_daily[o] if weights[o] else Decimal(0) for o in range(len(days))]
        return compound(own), compound(benchmark), weights

    def period_returns(path: list[Decimal], weights: list[Decimal] | None) -> dict:
        result = {}
        for period, base in bases.items():
            first = days.index(base)
            covered = weights is None or any(weights[first + 1 :])
            result[period] = f"{path[-1] / path[first] - 1:.6f}" if covered else None
        return result

    def row(kind: str, key: str, name: str, value: Decimal, group: str) -> dict:
        path, benchmark, weights = measure(group)
        return {
            "kind": kind,
            "key": key,
            "name": name,
            "value": str(value.quantize(CENTS)),
            "returns": period_returns(path, weights),
            # The CDI over the same days, so "% of the CDI" starts when the position did.
            "cdi": period_returns(benchmark, weights),
        }

    output = []
    if "" in weight:
        output.append(row("portfolio", "", "", held.get("", Decimal(0)), ""))
    ordered = sorted(members, key=lambda key: (not key, names.get(key, "")))
    for key in ordered:
        output.append(
            row("class", key, names.get(key, ""), held.get(key, Decimal(0)), f"class:{key}")
        )
        for member in sorted(members[key], key=lambda member: -member["value"]):
            output.append(
                row("position", member["key"], member["name"], member["value"], member["key"])
            )
    first = days.index(bases["12m"])

    def line(kind: str, key: str, name: str, path: list[Decimal]) -> dict:
        return {
            "kind": kind,
            "key": key,
            "name": name,
            "values": [f"{level / path[first] - 1:.6f}" for level in path[first:]],
        }

    lines = [line("cdi", "", "", compound(cdi_daily))]
    if "" in weight:
        lines.append(line("portfolio", "", "", measure("")[0]))
    lines += [
        line("class", key, names.get(key, ""), measure(f"class:{key}")[0])
        for key in ordered
        if f"class:{key}" in weight
    ]
    return {
        "end": str(end),
        "rows": output,
        "cdi": period_returns(compound(cdi_daily), None),
        "uncovered": uncovered,
        "series": {"days": [str(day) for day in days[first:]], "lines": lines},
    }
