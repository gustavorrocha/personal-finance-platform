from datetime import date
from decimal import Decimal

from finance_api import investment_history
from finance_api.investment_history import (
    CDI,
    ETF_STOCKS,
    FUNDS,
    INFLATION,
    PREFIXED,
    automatic_class,
    invested_history,
)

CLASSES = [
    {"id": CDI, "name": "Renda fixa - CDI"},
    {"id": INFLATION, "name": "Renda fixa - Inflação"},
    {"id": "e7f0", "name": "ETF renda fixa"},
]


def test_positions_are_preclassified_from_type_and_indexer():
    assert automatic_class({"type": "SAVINGS_BOX", "indexer": "CDI"}) == CDI
    assert automatic_class({"type": "FIXED_INCOME", "indexer": "SELIC"}) == CDI
    assert automatic_class({"type": "FIXED_INCOME", "indexer": "IPCA"}) == INFLATION
    assert automatic_class({"type": "FIXED_INCOME", "indexer": None}) == PREFIXED
    assert automatic_class({"type": "MUTUAL_FUND"}) == FUNDS
    assert automatic_class({"type": "EQUITY"}) == ETF_STOCKS
    assert automatic_class({"type": "COE"}) is None


def snapshot(position, day, balance, kind="FIXED_INCOME", indexer="IPCA", name="NTNB"):
    return {
        "position": position,
        "observed_on": day,
        "type": kind,
        "indexer": indexer,
        "name": name,
        "currency": "BRL",
        "balance": balance,
    }


def test_history_uses_stored_balances_walks_back_before_them_and_groups_by_class(
    monkeypatch,
):
    class Today(date):
        @classmethod
        def today(cls):
            return cls(2026, 11, 23)

    monkeypatch.setattr(investment_history, "date", Today)
    history = [
        # Stored balances this month: the last one counts, not the walk back.
        snapshot("ntnb", "2026-11-19", "1000"),
        snapshot("ntnb", "2026-11-22", "1010"),
        # Reported as an equity, assigned to a custom class by the operator.
        snapshot("etf", "2026-11-19", "500", kind="EQUITY", indexer=None, name="ETF"),
        # 500 went in, 100 came out, 50 is left: 350 paid bills without a withdrawal.
        snapshot("box", "2026-11-19", "50", kind="SAVINGS_BOX", indexer="CDI", name="Gastos"),
    ]
    flows = [
        {"position": "ntnb", "date": "2026-10-10", "net": "300"},
        {"position": "etf", "date": "2026-11-02", "net": "-200"},
        {"position": "box", "date": "2026-09-05", "net": "500"},
        {"position": "box", "date": "2026-10-20", "net": "-100"},
    ]
    rows, gaps = invested_history(history, flows, {"etf": "e7f0"}, CLASSES, "2026-11")
    totals = {(row["name"], row["month"]): Decimal(row["total"]) for row in rows}
    assert totals["Renda fixa - Inflação", "2026-11"] == 1010
    assert totals["Renda fixa - Inflação", "2026-09"] == 700
    assert totals["ETF renda fixa", "2026-10"] == 700
    assert totals["Renda fixa - CDI", "2026-08"] == 0
    assert totals["Renda fixa - CDI", "2026-10"] == 50
    assert gaps == [{"name": "Gastos", "currency": "BRL", "amount": "350"}]
    # A deleted class falls back to the automatic one.
    rows, _ = invested_history(history, flows, {"etf": "gone"}, CLASSES, "2026-11")
    assert "ETF renda fixa" not in {row["name"] for row in rows}
    assert "" in {row["key"] for row in rows}
