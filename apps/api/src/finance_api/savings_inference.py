"""Suggest bills that were paid straight from a savings box.

Mercado Pago does not report a boleto paid with a savings-box balance: only the box
shrinks. The evidence of such a payment is therefore a drop in the box balance that no
reported withdrawal explains.

- Since the first stored balance of a box, each drop between two observations is known:
  previous balance + reported contributions - reported withdrawals + expected yield -
  current balance. It becomes an "observed" suggestion with that amount and the days in
  between; a monthly bill whose amount and usual day fit names it. Daily syncs make the
  window a single day.
- Before that, providers expose no balance history: only the total that left is known.
  "Estimated" suggestions place monthly bills in months in which they were not reported,
  only while the box keeps a non-negative balance through every reported movement (with
  yield) and only up to that total.

The operator accepts or ignores each suggestion; nothing is recorded automatically.
"""

from collections import defaultdict
from datetime import date, timedelta
from statistics import mean, pstdev

# Fallback yield when no box allows estimating one: roughly 120% of a 13% CDI a year.
DEFAULT_DAILY_RATE = 0.00037
MAX_VARIATION = 0.35
# A drop matches a bill paid between 10% below and 10% above its observed range.
AMOUNT_TOLERANCE = 0.10

Entry = tuple[date, float]


def grow(entries: list[Entry], rate: float, until: date) -> float:
    return sum(amount * (1 + rate) ** max(0, (until - day).days) for day, amount in entries)


def implied_rate(entries: list[Entry], balance: float, today: date) -> float | None:
    """Daily rate that turns the box's reported flows into today's balance."""
    invested = grow(entries, 0, today)
    if not entries or invested <= 0 or balance <= invested:
        return None
    low, high = 0.0, 0.01
    for _ in range(80):
        middle = (low + high) / 2
        low, high = (middle, high) if grow(entries, middle, today) < balance else (low, middle)
    return low


def never_negative(entries: list[Entry], rate: float) -> bool:
    """The box can pay every reported withdrawal and suggested payment when it happens."""
    ordered = sorted(entries, key=lambda entry: (entry[0], -entry[1]))
    return all(
        grow(ordered[: index + 1], rate, day) >= -1 for index, (day, _) in enumerate(ordered)
    )


def month_range(first: str, last: str) -> list[str]:
    year, month = map(int, first.split("-"))
    months = []
    while f"{year:04d}-{month:02d}" <= last:
        months.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def monthly_bills(payments: list[dict]) -> list[dict]:
    """Payees paid with a stable amount in several months: likely monthly bills."""
    by_payee: dict[str, list[dict]] = defaultdict(list)
    for row in payments:
        by_payee[row["cnpj"]].append(row)
    bills = []
    for cnpj, rows in by_payee.items():
        amounts = [float(row["amount"]) for row in rows]
        seen = sorted({row["date"][:7] for row in rows})
        stable = mean(amounts) > 0 and pstdev(amounts) / mean(amounts) <= MAX_VARIATION
        if not stable or not (len(seen) >= 3 or (len(seen) >= 2 and mean(amounts) >= 500)):
            continue
        latest = max(rows, key=lambda row: row["date"])
        bills.append(
            {
                "cnpj": cnpj,
                "payee": latest["payee"],
                "item": latest["item"],
                "category_id": latest["category_id"],
                "category": latest["category"],
                "amount": round(mean(amounts), 2),
                "low": min(amounts),
                "high": max(amounts),
                "day": round(mean(int(row["date"][8:]) for row in rows)),
                "seen": seen,
            }
        )
    return bills


def suggest(
    boxes: list[dict],
    flows: list[dict],
    payments: list[dict],
    dismissed: set[tuple[str, str]],
    today: date,
    outflows: list[dict] | None = None,
) -> dict:
    """boxes: item, name, balance, pct, observed_since (first stored balance, ISO date).
    flows: item, box (lower name), date, kind, amount. payments: item, date, amount, cnpj,
    payee, category_id, category. dismissed: (cnpj, month). outflows (drops between two
    stored balances): item, box (name), start, end, amount, previous_balance.
    """
    entries: dict[tuple[str, str], list[Entry]] = defaultdict(list)
    for row in flows:
        sign = 1 if row["kind"] == "contribution" else -1
        entries[row["item"], row["box"]].append(
            (date.fromisoformat(row["date"]), sign * float(row["amount"]))
        )
    named = {(box["item"], box["name"].lower()): box for box in boxes}
    normalized = [
        rate / float(box["pct"])
        for key, box in named.items()
        if float(box["pct"] or 0) > 0
        and (rate := implied_rate(entries[key], float(box["balance"]), today)) is not None
    ]
    per_point = max(normalized, default=DEFAULT_DAILY_RATE / 120)

    def rate(key: tuple[str, str]) -> float:
        return per_point * float(named[key]["pct"] or 120 if key in named else 120)

    # Total that left each box without a reported withdrawal, yield removed.
    gaps = {
        key: grow(entries[key], rate(key), today) - float(box["balance"])
        for key, box in named.items()
        if entries[key]
    }
    bills = monthly_bills(payments)
    suggestions: list[dict] = []

    # 1. Observed drops: exact amount, named by a bill that fits amount and day.
    observed_total: dict[tuple[str, str], float] = defaultdict(float)
    for drop in outflows or []:
        key = drop["item"], drop["box"].lower()
        start, end = date.fromisoformat(drop["start"]), date.fromisoformat(drop["end"])
        # The balance earned yield between the two observations, which hid part of the
        # payment: add it back to get the bill's full value.
        earned = float(drop.get("previous_balance") or 0) * (
            (1 + rate(key)) ** (end - start).days - 1
        )
        amount = float(drop["amount"]) + earned
        observed_total[key] += amount
        window = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
        fits = [
            (abs(amount - bill["amount"]), bill, day)
            for bill in bills
            if bill["item"] == drop["item"]
            and bill["low"] * (1 - AMOUNT_TOLERANCE)
            <= amount
            <= bill["high"] * (1 + AMOUNT_TOLERANCE)
            for day in window
            if day.day == min(bill["day"], 28) and day.strftime("%Y-%m") not in bill["seen"]
        ]
        if not fits:
            # An unnamed drop already waits in Debit review as a savings-box outflow.
            continue
        _, bill, day = min(fits, key=lambda fit: fit[0])
        month = day.strftime("%Y-%m")
        if (bill["cnpj"], month) in dismissed:
            continue
        suggestions.append(
            {
                "kind": "observed",
                "month": month,
                "date": day,
                **{
                    field: bill[field]
                    for field in (
                        "cnpj",
                        "payee",
                        "category_id",
                        "category",
                        "low",
                        "high",
                    )
                },
                "item": drop["item"],
                "amount": round(amount, 2),
                "box": named[key]["name"] if key in named else drop["box"],
                "window": [start.isoformat(), end.isoformat()],
                "key": key,
            }
        )

    # 2. Before the first stored balance: place missing bill months while every box stays
    # solvent through its reported movements, up to what left it unobserved.
    candidates = [
        {**bill, "month": month, "date": when}
        for bill in bills
        for month in month_range(bill["seen"][0], bill["seen"][-1])
        if month not in bill["seen"]
        and (bill["cnpj"], month) not in dismissed
        and (when := date(*map(int, month.split("-")), min(bill["day"], 28))) <= today
    ]
    placed: dict[tuple[str, str], list[Entry]] = defaultdict(list)
    for candidate in sorted(candidates, key=lambda row: row["date"]):
        options = []
        for key, box in named.items():
            since = date.fromisoformat(box.get("observed_since") or today.isoformat())
            unobserved = gaps.get(key, 0) - observed_total[key]
            remaining = unobserved - sum(-amount for _, amount in placed[key])
            if (
                key[0] != candidate["item"]
                or candidate["date"] >= since
                or remaining < candidate["amount"] * 0.9
            ):
                continue
            trial = entries[key] + placed[key] + [(candidate["date"], -candidate["amount"])]
            if never_negative(trial, rate(key)):
                options.append((remaining, box["name"], key))
        if options:
            _, name, key = max(options)
            placed[key].append((candidate["date"], -candidate["amount"]))
            suggestions.append(
                {
                    **{
                        field: candidate[field]
                        for field in (
                            "month",
                            "date",
                            "cnpj",
                            "payee",
                            "item",
                            "category_id",
                            "category",
                            "amount",
                            "low",
                            "high",
                        )
                    },
                    "kind": "estimated",
                    "box": name,
                    "window": None,
                    "key": key,
                }
            )

    covered: dict[tuple[str, str], float] = defaultdict(float)
    for row in suggestions:
        covered[row["key"]] += row["amount"]
    return {
        "daily_rate": per_point * 120,
        "gaps": [
            {
                "item": key[0],
                "box": named[key]["name"],
                "amount": round(gap, 2),
                "observed": round(observed_total[key], 2),
                "suggested": round(covered[key], 2),
                "observed_since": named[key].get("observed_since"),
            }
            for key, gap in gaps.items()
            if gap >= 1
        ],
        "suggestions": [
            {
                **{field: value for field, value in row.items() if field != "key"},
                "date": row["date"].isoformat(),
                "day": row["date"].day,
            }
            for row in sorted(suggestions, key=lambda row: row["date"])
        ],
    }
