from datetime import date, timedelta

from finance_api.savings_inference import suggest

ITEM = "item-1"
TODAY = date(2026, 3, 20)
BOXES = [
    {"item": ITEM, "name": "Gastos", "balance": "0", "pct": "120"},
    # Only grew: its balance gives the yield used to discount every box.
    {"item": ITEM, "name": "Reserva", "balance": "1010", "pct": "120"},
]
FLOWS = [
    *(
        {"item": ITEM, "box": "gastos", "date": day, "kind": "contribution", "amount": "1000"}
        for day in ("2026-01-02", "2026-02-02", "2026-03-02")
    ),
    {
        "item": ITEM,
        "box": "reserva",
        "date": "2026-01-01",
        "kind": "contribution",
        "amount": "1000",
    },
]


def payment(cnpj, day, amount, payee):
    return {
        "item": ITEM,
        "date": day,
        "amount": amount,
        "cnpj": cnpj,
        "payee": payee,
        "category_id": "cat",
        "category": "Moradia › Aluguel",
    }


PAYMENTS = [
    payment("1" * 14, "2026-01-05", "950", "Imobiliária"),
    payment("1" * 14, "2026-03-05", "960", "Imobiliária"),
    # Small and seen in only two months: not a reliable monthly bill.
    payment("2" * 14, "2026-01-10", "30", "Lanchonete"),
    payment("2" * 14, "2026-03-10", "31", "Lanchonete"),
]


def test_missing_month_of_a_monthly_bill_is_suggested_from_a_box_with_money():
    result = suggest(BOXES, FLOWS, PAYMENTS, set(), TODAY)
    # 1000 became 1010 in 78 days.
    assert 0.00012 < result["daily_rate"] < 0.00014
    assert [
        (row["month"], row["payee"], row["amount"], row["box"], row["day"])
        for row in result["suggestions"]
    ] == [("2026-02", "Imobiliária", 955.0, "Gastos", 5)]
    gastos = next(gap for gap in result["gaps"] if gap["box"] == "Gastos")
    assert gastos["amount"] > 3000 and gastos["suggested"] == 955.0
    assert "Reserva" not in {gap["box"] for gap in result["gaps"]}


def test_ignored_months_and_boxes_without_money_are_not_suggested():
    assert suggest(BOXES, FLOWS, PAYMENTS, {("1" * 14, "2026-02")}, TODAY)["suggestions"] == []
    empty = [{**box, "balance": "3000"} for box in BOXES[:1]]
    assert suggest(empty, FLOWS[:3], PAYMENTS, set(), TODAY)["suggestions"] == []


def test_dismissing_a_suggestion_requires_local_origin_and_a_valid_cnpj(monkeypatch):
    from fastapi.testclient import TestClient
    from finance_api import spending
    from finance_api.main import app

    writes = []

    async def record(query, **parameters):
        writes.append(parameters)
        return []

    monkeypatch.setattr(spending, "dashboard_query", record)
    path = "/api/spending/savings-box-suggestions/dismiss"
    body = {"cnpj": "1" * 14, "month": "2026-02"}
    local = {"Origin": "http://127.0.0.1:8080"}
    with TestClient(app) as client:
        assert client.post(path, json=body).status_code == 403
        assert client.post(path, headers=local, json={**body, "cnpj": "12"}).status_code == 422
        assert not writes
        assert client.post(path, headers=local, json=body).status_code == 204
    assert writes == [{"cnpj": "1" * 14, "month": "2026-02-01"}]


def test_an_observed_drop_keeps_its_exact_amount_and_is_named_by_a_fitting_bill():
    boxes = [
        {**BOXES[0], "observed_since": "2026-03-01"},
        {**BOXES[1], "observed_since": "2026-03-01"},
    ]
    payments = [
        payment("1" * 14, "2026-01-05", "950", "Imobiliária"),
        payment("1" * 14, "2026-02-05", "960", "Imobiliária"),
    ]
    drop = {"item": ITEM, "box": "Gastos", "start": "2026-03-03", "end": "2026-03-06"}
    result = suggest(boxes, FLOWS, payments, set(), TODAY, [{**drop, "amount": "958.40"}])
    observed = [row for row in result["suggestions"] if row["kind"] == "observed"]
    assert [(row["date"], row["payee"], row["amount"]) for row in observed] == [
        ("2026-03-05", "Imobiliária", 958.4)
    ]
    assert observed[0]["window"] == ["2026-03-03", "2026-03-06"]
    # A drop no bill explains stays in Debit review only.
    odd = suggest(boxes, FLOWS, payments, set(), TODAY, [{**drop, "amount": "120"}])
    assert not [row for row in odd["suggestions"] if row["kind"] == "observed"]


def test_an_estimated_payment_must_leave_money_for_every_later_withdrawal():
    flows = [
        {
            "item": ITEM,
            "box": "gastos",
            "date": "2026-01-02",
            "kind": "contribution",
            "amount": "1000",
        },
        # Reported: the box paid this out in full, so it could not have paid rent before it.
        {
            "item": ITEM,
            "box": "gastos",
            "date": "2026-02-20",
            "kind": "withdrawal",
            "amount": "1000",
        },
        {
            "item": ITEM,
            "box": "gastos",
            "date": "2026-03-01",
            "kind": "contribution",
            "amount": "1000",
        },
        FLOWS[3],
    ]
    payments = [
        payment("1" * 14, "2026-01-05", "950", "Imobiliária"),
        payment("1" * 14, "2026-03-05", "960", "Imobiliária"),
    ]
    result = suggest(BOXES, flows, payments, set(), TODAY)
    assert result["suggestions"] == []
    assert next(gap for gap in result["gaps"] if gap["box"] == "Gastos")["amount"] > 990


def test_box_yield_follows_the_cdi_on_business_days():
    # 0.1% a business day at 120% of the CDI: only weekdays earn.
    cdi = [
        {"day": str(date(2026, 1, 1) + timedelta(days=n)), "value": "0.1"}
        for n in range(80)
        if (date(2026, 1, 1) + timedelta(days=n)).weekday() < 5
    ]
    boxes = [{"item": ITEM, "name": "Gastos", "balance": "1000", "pct": "120"}]
    flows = [FLOWS[0]]  # 1000 in on 2026-01-02, never withdrawn
    result = suggest(boxes, flows, [], set(), TODAY, [], cdi)
    business = sum(1 for row in cdi if "2026-01-02" <= row["day"] < "2026-03-20")
    earned = 1000 * (1 + 0.0012) ** business - 1000
    # What it should hold minus what it holds: the yield it earned left without a trace.
    (gap,) = result["gaps"]
    assert gap["amount"] == round(earned, 2)
    assert 0.0008 < result["daily_rate"] < 0.0009  # 0.12% on 5 of every 7 days


def test_established_bills_continue_after_their_last_month_from_any_connection():
    today = date(2026, 11, 23)
    box = {
        "item": ITEM,
        "name": "Gastos",
        "balance": "500",
        "pct": "120",
        "observed_since": "2026-11-19",
    }
    flows = [{**FLOWS[0], "date": "2026-01-02"}]
    # Electricity paid from another connection for six months up to August.
    light = [
        {**payment("3" * 14, f"2026-{month:02d}-06", "150", "Light"), "item": "other-bank"}
        for month in range(3, 9)
    ]
    # Three months only: it may have ended, so it is not carried forward.
    short = [payment("4" * 14, f"2026-{month:02d}-08", "38", "Loja") for month in (4, 5, 6)]
    result = suggest([box], flows, light + short, set(), today)
    assert [(row["month"], row["payee"], row["item"]) for row in result["suggestions"]] == [
        ("2026-09", "Light", ITEM),
        ("2026-10", "Light", ITEM),
        ("2026-11", "Light", ITEM),
    ]
