from datetime import date, timedelta
from decimal import Decimal

import pytest
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
        "item": f"connection-{position}",
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
    rows, gaps, positions = invested_history(
        history, flows, {"etf": "e7f0"}, CLASSES, "2026-11", position_month="2026-10"
    )
    totals = {(row["name"], row["month"]): Decimal(row["total"]) for row in rows}
    assert totals["Renda fixa - Inflação", "2026-11"] == 1010
    assert totals["Renda fixa - Inflação", "2026-09"] == 700
    assert totals["ETF renda fixa", "2026-10"] == 700
    assert totals["Renda fixa - CDI", "2026-08"] == 0
    assert totals["Renda fixa - CDI", "2026-10"] == 50
    assert {row["item"]: row["value"] for row in positions} == {
        "connection-ntnb": "1000.00",
        "connection-etf": "700.00",
        "connection-box": "50.00",
    }
    assert gaps == [{"name": "Gastos", "currency": "BRL", "amount": "350.00"}]
    # A deleted class falls back to the automatic one.
    rows, _, _ = invested_history(history, flows, {"etf": "gone"}, CLASSES, "2026-11")
    assert "ETF renda fixa" not in {row["name"] for row in rows}
    assert "" in {row["key"] for row in rows}


def test_curve_positions_earn_their_rate_on_business_days_only(monkeypatch):
    class Today(date):
        @classmethod
        def today(cls):
            return cls(2026, 11, 23)

    monkeypatch.setattr(investment_history, "date", Today)
    # 1% a business day keeps the arithmetic readable; Friday 2026-10-30 to Monday 11-02
    # earns once, and the holiday 11-20 (absent from the series) earns nothing.
    business = [
        date(2026, 10, 1) + timedelta(days=n)
        for n in range(60)
        if (date(2026, 10, 1) + timedelta(days=n)).weekday() < 5
        and date(2026, 10, 1) + timedelta(days=n) != date(2026, 11, 20)
    ]
    rates = [{"series": "CDI", "day": str(day), "value": "1"} for day in business]
    lca = snapshot("lca", "2026-11-19", "1000", indexer="CDI", name="LCA") | {
        "rate": "50",  # 50% of the CDI: 0.5% a business day
        "purchase_date": "2026-11-03",
        "gross": "1000",
    }
    cdb = snapshot("cdb", "2026-11-19", "900", indexer=None, name="CDB") | {
        "subtype": "CDB",
        "fixed_rate": "10",
        "gross": "1000",  # balance net of income tax; the gross one is valued
    }
    values, _ = investment_history.daily_values(
        [lca], [], date(2026, 10, 31), {"CDI": {day: Decimal(1) for day in business}}
    )
    # Observed on 11-19, the balance is the close of 11-18.
    days_back = sum(date(2026, 11, 3) <= day < date(2026, 11, 18) for day in business)
    assert values[date(2026, 11, 3)] == pytest.approx(Decimal(1000) / Decimal("1.005") ** days_back)
    assert values[date(2026, 11, 2)] == 0  # before the purchase
    # Forward to today: 11-18 and 19 earn, 11-20 is a holiday, 11-21 and 22 a weekend.
    assert values[date(2026, 11, 23)] == pytest.approx(Decimal(1000) * Decimal("1.005") ** 2)
    rows, gaps, _ = invested_history(
        [lca, cdb],
        [],
        {},
        CLASSES + [{"id": PREFIXED, "name": "Renda fixa - Pré"}],
        "2026-11",
        rates,
    )
    totals = {(row["name"], row["month"]): Decimal(row["total"]) for row in rows}
    step = Decimal(1.1 ** (1 / 252))
    du = sum(date(2026, 10, 31) <= day < date(2026, 11, 18) for day in business)
    assert totals["Renda fixa - Pré", "2026-10"] == pytest.approx(
        Decimal(1000) / step**du, abs=Decimal("0.01")
    )
    assert gaps == []


def test_treasury_bonds_follow_their_price_from_day_to_day():
    bond = snapshot("ltn", "2026-11-19", "900", indexer=None, name="Tesouro Prefixado 2032 (LTN)")
    bond |= {"subtype": "TREASURY", "due_date": "2032-01-01", "gross": "1000"}
    assert investment_history.asset_key(bond) == "Tesouro Prefixado|2032-01-01"
    # Friday 11-13 at 400, Monday 11-16 at 500 (no weekend prices), 11-18 at 500.
    prices = {date(2026, 11, 13): Decimal(400), date(2026, 11, 16): Decimal(500)}
    prices[date(2026, 11, 18)] = Decimal(500)
    # 100 bought on Monday: before it, 900 at Monday's 500 was 720 at Friday's 400.
    flows = [(date(2026, 11, 16), Decimal(100))]
    values, _ = investment_history.daily_values([bond], flows, date(2026, 11, 1), {}, prices)
    assert values[date(2026, 11, 18)] == 1000  # observed 11-19: the 11-18 close
    assert values[date(2026, 11, 16)] == 1000
    assert values[date(2026, 11, 15)] == 720  # weekend at Friday's price
    assert values[date(2026, 11, 13)] == 720
    assert values[date(2026, 11, 12)] == 720  # before the first price, no change


def test_funds_and_listed_assets_are_keyed_by_cnpj_and_ticker():
    fund = {"type": "MUTUAL_FUND", "symbol": "12.345.678/0001-90"}
    assert investment_history.asset_key(fund) == "12345678000190"
    assert investment_history.asset_key({"type": "EQUITY", "symbol": "etfx11"}) == "ETFX11"
    assert investment_history.asset_key({"type": "EQUITY", "symbol": "BR STN"}) is None


def test_returns_follow_each_model_weighted_by_value_and_ignore_flows(monkeypatch):
    class Today(date):
        @classmethod
        def today(cls):
            return cls(2026, 11, 24)

    monkeypatch.setattr(investment_history, "date", Today)
    business = [
        date(2025, 11, 1) + timedelta(days=n)
        for n in range(390)
        if (date(2025, 11, 1) + timedelta(days=n)).weekday() < 5
    ]
    rates = [{"series": "CDI", "day": str(day), "value": "0.05"} for day in business]
    lca = snapshot("lca", "2026-11-20", "1000", indexer="CDI", name="LCA") | {"rate": "100"}
    bond = snapshot(
        "ntnb",
        "2026-11-20",
        "1000",
        indexer="IPCA",
        name="Tesouro IPCA+ com Juros Semestrais 2037 (NTNB)",
    )
    bond |= {"subtype": "TREASURY", "due_date": "2037-05-15"}
    # The bond loses 1% on 11-10 and drops 3% on the 11-16 coupon payment.
    prices = [
        {
            "asset": "Tesouro IPCA+ com Juros Semestrais|2037-05-15",
            "day": str(day),
            "price": str(price),
        }
        for day, price in [
            (date(2026, 10, 30), 100),
            (date(2026, 11, 10), 99),
            (date(2026, 11, 16), 96),
            (date(2026, 11, 19), 96),
        ]
    ]
    # A purchase in the month changes the value, not the return.
    flows = [{"position": "lca", "date": "2026-11-05", "net": "500"}]
    result = investment_history.invested_returns([lca, bond], flows, {}, CLASSES, rates, prices)
    returns = {row["name"] or row["kind"]: row["returns"] for row in result["rows"]}
    november = sum(date(2026, 10, 31) <= day < date(2026, 11, 23) for day in business)
    assert Decimal(returns["LCA"]["month"]) == pytest.approx(
        Decimal("1.0005") ** november - 1, abs=Decimal("1e-6")
    )
    assert Decimal(returns[bond["name"]]["month"]) == pytest.approx(
        Decimal("-0.01"), abs=Decimal("1e-6")
    )
    portfolio = Decimal(returns["portfolio"]["month"])
    assert Decimal(returns[bond["name"]]["month"]) < portfolio < Decimal(returns["LCA"]["month"])
    assert Decimal(result["cdi"]["month"]) == Decimal(returns["LCA"]["month"])
    assert result["uncovered"] == [] and result["series"]["days"][-1] == "2026-11-23"


def test_cdi_comparison_starts_when_the_position_was_bought(monkeypatch):
    class Today(date):
        @classmethod
        def today(cls):
            return cls(2026, 11, 24)

    monkeypatch.setattr(investment_history, "date", Today)
    business = [
        date(2025, 11, 1) + timedelta(days=n)
        for n in range(390)
        if (date(2025, 11, 1) + timedelta(days=n)).weekday() < 5
    ]
    rates = [{"series": "CDI", "day": str(day), "value": "0.05"} for day in business]
    lca = snapshot("lca", "2026-11-20", "1000", indexer="CDI", name="LCA")
    lca |= {"rate": "100", "purchase_date": "2026-11-10"}
    result = investment_history.invested_returns([lca], [], {}, CLASSES, rates, [])
    position = next(row for row in result["rows"] if row["kind"] == "position")
    held = sum(date(2026, 11, 10) <= day < date(2026, 11, 22) for day in business)
    expected = Decimal("1.0005") ** held - 1
    assert Decimal(position["returns"]["12m"]) == pytest.approx(expected, abs=Decimal("1e-6"))
    assert position["cdi"]["12m"] == position["returns"]["12m"]  # 100% of the CDI
    assert Decimal(result["cdi"]["12m"]) > expected  # the full-period CDI is longer
    kinds = [line["kind"] for line in result["series"]["lines"]]
    assert kinds == ["cdi", "portfolio", "class"]


def test_chart_lines_start_when_their_class_entered(monkeypatch):
    class Today(date):
        @classmethod
        def today(cls):
            return cls(2026, 11, 24)

    monkeypatch.setattr(investment_history, "date", Today)
    business = [
        date(2025, 11, 1) + timedelta(days=n)
        for n in range(390)
        if (date(2025, 11, 1) + timedelta(days=n)).weekday() < 5
    ]
    rates = [{"series": "CDI", "day": str(day), "value": "0.05"} for day in business]
    lca = snapshot("lca", "2026-11-20", "1000", indexer="CDI", name="LCA")
    lca |= {"rate": "110", "purchase_date": "2026-11-10"}
    result = investment_history.invested_returns([lca], [], {}, CLASSES, rates, [])
    days = result["series"]["days"]
    line = next(line for line in result["series"]["lines"] if line["kind"] == "class")
    entered = days.index("2026-11-10")  # the purchase day: the first one with a value
    assert line["values"][entered - 1] is None and line["values"][entered] == "0.000000"
    assert line["excess"][entered] == "0.000000"
    # 110% of the CDI: ahead of it from the purchase on, whatever happened before.
    assert Decimal(line["excess"][-1]) > 0
    cdi = result["series"]["lines"][0]
    assert cdi["kind"] == "cdi" and cdi["values"][0] == "0.000000"
