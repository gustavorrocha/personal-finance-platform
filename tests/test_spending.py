import json
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from finance_api import investments, spending
from finance_api.main import app
from finance_ingestion.collection import entity_key, item_key
from finance_ingestion.silver import transaction_details
from finance_ingestion.spending import spending_fields
from finance_ingestion.spending_demo import load_demo
from finance_lake.bronze import CapturePage
from finance_lake.manifest import json_bytes

from tests.test_provider_ingestion import CARD, ITEM, NEW_ITEM, WHEN
from tests.test_provider_ingestion import isolated_warehouse as isolated_warehouse
from tests.test_provider_ingestion import pipeline as pipeline


def test_transaction_details_preserve_bank_text_and_distinguish_reported_time():
    details = transaction_details(
        {
            "description": "Normalized description",
            "descriptionRaw": "COMPRA *Loja <&>",
            "date": "2026-11-17T21:15:00-03:00",
            "creditCardMetadata": {
                "purchaseDate": "2026-10-17",
                "installmentNumber": 2,
                "totalInstallments": 5,
                "totalAmount": 200,
            },
        }
    )
    assert details["bank_description"] == "COMPRA *Loja <&>"
    assert details["transaction_time"] == "2026-11-18 00:15:00.000000"
    assert details["original_purchase_date"] == "2026-10-17"
    assert (details["installment_number"], details["total_installments"]) == (2, 5)
    assert Decimal(details["installment_total_amount"]) == 200
    for missing_time in ("2026-11-17", "2026-11-17T00:00:00Z"):
        assert transaction_details({"date": missing_time})["transaction_time"] is None


def test_investment_flows_cover_savings_boxes_and_fixed_income_and_are_not_spending():
    cases = [
        ({"type": "DEBIT", "description": "Dinheiro reservado Viagem"}, "contribution"),
        ({"type": "CREDIT", "description": "Dinheiro retirado Viagem"}, "withdrawal"),
        (
            {"type": "DEBIT", "description": "COMPRA - CDB BANCO X - VENC.: 01-01-2030"},
            "contribution",
        ),
        ({"type": "CREDIT", "description": "VENCIMENTO - LCA BANCO X"}, "withdrawal"),
        (
            {
                "type": "CREDIT",
                "description": "Rendimentos",
                "category": "Proceeds interests and dividends",
            },
            "income",
        ),
        ({"type": "DEBIT", "description": "IRRF - CDB BANCO X"}, "income"),
        (
            {"type": "DEBIT", "description": "Aplicação automática", "category": "Investments"},
            "contribution",
        ),
        ({"type": "CREDIT", "description": "Resgate", "category": "Fixed income"}, "withdrawal"),
        ({"type": "DEBIT", "description": "Compra - Mercado X", "category": "Groceries"}, ""),
    ]
    for record, kind in cases:
        fields = spending_fields(record, "tx")
        assert fields["investment_kind"] == kind, record
        if kind:
            assert fields["spending_kind"] == ""
    card = {"type": "DEBIT", "description": "Dinheiro reservado X", "creditCardMetadata": {}}
    assert spending_fields(card, "tx", card_account=True)["investment_kind"] == ""


def test_spending_requires_purchase_evidence_and_excludes_transfers_and_settlements():
    debit = {"type": "DEBIT", "description": "Synthetic Market"}
    assert spending_fields(debit, "tx")["spending_kind"] == "review"
    card = {**debit, "creditCardMetadata": {}, "category": "Groceries"}
    assert spending_fields(card, "tx")["spending_kind"] == "purchase"
    assert spending_fields(card, "tx")["spending_category"] == "Groceries"
    for operation in ("TRANSFER", "PAGAMENTO_FATURA"):
        assert spending_fields({**card, "operationType": operation}, "tx")["spending_kind"] == ""
    for operation in ("PIX", "TED"):
        assert (
            spending_fields({**debit, "operationType": operation}, "tx")["spending_operation"]
            == operation
        )
        assert (
            spending_fields({**debit, "operationType": operation}, "tx")["spending_kind"]
            == "review"
        )
        assert (
            spending_fields({**debit, "operationType": operation, "category": "Transfer"}, "tx")[
                "spending_kind"
            ]
            == ""
        )
    refund = {**card, "type": "CREDIT", "operationType": "ESTORNO"}
    assert spending_fields(refund, "tx")["spending_kind"] == "refund"
    assert (
        spending_fields(refund, "tx")["merchant_key"] == spending_fields(card, "tx")["merchant_key"]
    )
    assert "Synthetic Market" not in str(spending_fields(card, "tx"))
    assert (
        spending_fields({**debit, "operationType": "private-text"}, "tx")["spending_operation"]
        == ""
    )
    cafe = {"type": "DEBIT", "merchant": {"name": "Synthetic Café"}}
    assert spending_fields(cafe, "tx")["spending_category"] == "Dining"


def test_category_corrections_require_local_origin_and_validate_before_database(monkeypatch):
    async def unexpected(*args, **kwargs):
        pytest.fail("Rejected requests should not reach ClickHouse")

    monkeypatch.setattr(spending, "dashboard_query", unexpected)
    body = {
        "item": "10000000-0000-4000-8000-100000000001",
        "transaction": "10000000-0000-4000-8000-100000000002",
        "category": "Dining",
    }
    with TestClient(app) as client:
        assert client.post("/api/spending/rules", json=body).status_code == 403
        external = {"Origin": "https://example.test"}
        assert client.post("/api/spending/rules", headers=external, json=body).status_code == 403
        local = {"Origin": "http://127.0.0.1:8080"}
        rejected = client.post(
            "/api/spending/rules", headers=local, json={**body, "category": "private-text-mock"}
        )
        assert rejected.status_code == 422
        assert rejected.json() == {"detail": "Invalid request"}
        review = {"item": body["item"], "transaction": body["transaction"], "decision": "include"}
        assert (
            client.post("/api/spending/reviews", headers=external, json=review).status_code == 403
        )
        oversized = {"item": body["item"], "transactions": [body["transaction"]] * 5}
        assert (
            client.post("/api/spending/suggestions", headers=local, json=oversized).status_code
            == 422
        )


def test_dashboard_describes_demo_without_relying_on_english_labels(monkeypatch):
    async def connections(_query):
        return [
            {"id": spending.DEMO_ITEM, "latest_month": "2026-11"},
            {"id": "10000000-0000-4000-8000-100000000001", "latest_month": "2026-11"},
        ]

    monkeypatch.setattr(spending, "dashboard_query", connections)
    with TestClient(app) as client:
        page = client.get("/api/spending").json()
        assert [row["is_demo"] for row in page["connections"]] == [True, False]


def test_combined_spending_includes_bank_and_card_and_keeps_edits_scoped(
    isolated_warehouse, monkeypatch
):
    silver = isolated_warehouse()
    load_demo(silver)

    def observe(source, account_type, records, observed=WHEN):
        item = item_key(source)
        rows = [
            {
                "id": str(uuid4()),
                "accountId": CARD,
                "type": "DEBIT",
                "status": "POSTED",
                "date": "2024-11-10",
                "currencyCode": "BRL",
                **record,
            }
            for record in records
        ]
        manifest = silver.lake.commit(
            run_id=uuid4(),
            retrieved_at=observed,
            item_alias=f"item-{item.hex}",
            capture_kind="full",
            payloads=[
                CapturePage(
                    "items",
                    json_bytes({"id": source, "status": "UPDATED", "connector": {"id": 123}}),
                ),
                CapturePage("accounts", json_bytes({"results": [account(account_type)]})),
                CapturePage(
                    "transactions",
                    json_bytes({"results": rows}),
                    entity_key(item, "accounts", CARD),
                ),
            ],
        )
        silver.replay(manifest.run_id)

    def account(account_type):
        record = {"id": CARD, "type": account_type, "currencyCode": "BRL"}
        if account_type == "BANK":
            remuneration = {"indexer": "CDI", "postFixedIndexerPercentage": 1.2}
            boxes = [("Viagem", 7.25, "BRL"), ("Casa", 0, "BRL"), ("Reserva", 3, "BRL")]
            boxes.append(("Dolares", 50, "USD"))
            record["bankData"] = {
                "reservedBalances": [
                    {
                        "name": name,
                        "identification": name.lower(),
                        "availableAmounts": [
                            {"amount": amount, "currencyCode": code, "remuneration": remuneration}
                        ],
                    }
                    for name, amount, code in boxes
                ]
            }
        return record

    observe(
        ITEM,
        "BANK",
        [
            {"amount": 10, "operationType": "CARTAO"},
            {"amount": 20, "operationType": "CARTAO", "date": "2024-10-05"},
            {"amount": 100, "description": "Dinheiro reservado Viagem", "category": "Other"},
            {"amount": 30, "type": "CREDIT", "description": "Dinheiro retirado Viagem"},
            {
                "amount": 2,
                "type": "CREDIT",
                "description": "Rendimentos",
                "category": "Proceeds interests and dividends",
            },
            {"amount": 0.5, "description": "IRRF - CDB Banco X"},
            {"amount": 100, "operationType": "TRANSFERENCIA_MESMA_INSTITUICAO"},
            {
                "amount": 7,
                "paymentData": {"paymentMethod": "PIX"},
                "description": "private details",
            },
        ],
    )
    pending_purchase = {
        "id": str(uuid4()),
        "amount": 8,
        "operationType": "PAGAMENTO",
        "creditCardMetadata": {"installmentNumber": 2, "totalInstallments": 4},
        "status": "PENDING",
        "descriptionRaw": "COMPRA *Loja de teste",
        "date": "2024-11-10T16:25:00Z",
        "category": "Office supplies",
    }
    observe(
        NEW_ITEM,
        "CREDIT",
        [
            {"amount": 25, "operationType": "PAGAMENTO", "creditCardMetadata": {}},
            {"amount": 55, "type": "CREDIT", "operationType": "PAGAMENTO_FATURA"},
            pending_purchase,
            {**pending_purchase, "id": str(uuid4()), "amount": -9},
            {**pending_purchase, "id": str(uuid4()), "amount": 60, "type": "CREDIT"},
            {
                **pending_purchase,
                "id": str(uuid4()),
                "amount": 90,
                "operationType": "PAGAMENTO_FATURA",
            },
        ],
    )

    async def execute(query, **parameters):
        return [json.loads(line) for line in silver.execute(query, **parameters).splitlines()]

    def total(page):
        return Decimal(next(row["total"] for row in page["totals"] if row["bucket"] is None))

    monkeypatch.setattr(spending, "dashboard_query", execute)
    monkeypatch.setattr(investments, "dashboard_query", execute)

    def execute_sql(query):
        return silver.execute(query).decode()

    path = "/api/spending"
    with TestClient(app) as client:
        result = client.get(path, params={"item": "all"})
        assert result.status_code == 200
        page = result.json()
        assert page["selected"]["id"] == "all"
        assert page["month"] == "2024-11"
        assert total(page) == Decimal(35)
        history = {}
        for row in page["history"]:
            key = (row["month"], row["source"], row["status"])
            history[key] = history.get(key, 0) + Decimal(row["total"])
        assert history == {
            ("2024-10", "bank", "POSTED"): Decimal(20),
            ("2024-11", "bank", "POSTED"): Decimal(10),
            ("2024-11", "card", "POSTED"): Decimal(25),
            ("2024-11", "card", "PENDING"): Decimal(8),
        }
        assert {row["kind"]: Decimal(row["total"]) for row in page["investments"]} == {
            "contribution": Decimal(100),
            "withdrawal": Decimal(30),
            "income": Decimal("1.5"),
        }
        assert [(row["currency"], row["source"], row["total"]) for row in page["invested"]] == [
            ("BRL", "savings_boxes", "10.25")
        ]
        boxes = execute_sql(
            "SELECT name, currency, toString(balance), toString(indexer_percentage) "
            "FROM analytics.savings_boxes ORDER BY name FORMAT TSV"
        )
        assert boxes.splitlines() == [
            "Casa	BRL	0	120",
            "Dolares	USD	50	120",
            "Reserva	BRL	3	120",
            "Viagem	BRL	7.25	120",
        ]
        flows = execute_sql(
            "SELECT kind, savings_box FROM analytics.investment_flows "
            "WHERE savings_box != '' ORDER BY kind FORMAT TSV"
        )
        assert flows.splitlines() == ["contribution	Viagem", "withdrawal	Viagem"]
        positions = client.get("/api/investments", params={"item": str(item_key(ITEM))}).json()
        assert {row["name"] for row in positions["positions"]} == {
            "Casa",
            "Dolares",
            "Reserva",
            "Viagem",
        }
        assert {row["category"] for row in page["history"] if row["status"] == "PENDING"} == {
            "Office supplies"
        }
        assert {row["item"] for row in page["expenses"]} == {
            str(item_key(s)) for s in (ITEM, NEW_ITEM)
        }
        review = page["reviews"][0]
        assert review["operation"] == "PIX" and review["merchant"] == ""
        assert review["description"] == "private details"
        searched = client.get(path, params={"item": "all", "search": "office supplies"}).json()
        assert total(searched) == Decimal(35)
        assert len(searched["expenses"]) == 1
        purchase = searched["expenses"][0]
        assert purchase["description"] == "COMPRA *Loja de teste"
        assert purchase["status"] == "PENDING"
        assert purchase["category"] == "Office supplies"
        assert purchase["transaction_time"] == "2024-11-10T16:25:00.000000Z"
        assert (purchase["installment_number"], purchase["total_installments"]) == (2, 4)
        monkeypatch.setattr(spending, "EXPENSE_PAGE_SIZE", 1)
        first = client.get(path, params={"item": "all"}).json()
        second = client.get(path, params={"item": "all", "page": 2}).json()
        assert first["has_more_expenses"]
        assert first["expenses"][0]["id"] != second["expenses"][0]["id"]
        monkeypatch.setattr(spending, "EXPENSE_PAGE_SIZE", 100)
        response = client.post(
            path + "/reviews",
            headers={"Origin": "http://127.0.0.1:8080"},
            json={"item": review["item"], "transaction": review["id"], "decision": "include"},
        )
        assert response.status_code == 204
        assert total(client.get(path, params={"item": "all"}).json()) == Decimal(42)
        assert total(client.get(path, params={"item": str(item_key(NEW_ITEM))}).json()) == Decimal(
            25
        )
        observe(
            NEW_ITEM,
            "CREDIT",
            [{**pending_purchase, "status": "POSTED"}],
            observed=WHEN + timedelta(days=1),
        )
        settled = client.get(path, params={"item": "all"}).json()
        assert total(settled) == Decimal(50)
        assert {row["status"] for row in settled["history"] if row["month"] == "2024-11"} == {
            "POSTED"
        }


def test_dashboard_excludes_nonexpenses_and_rules_survive_replay(isolated_warehouse, monkeypatch):
    silver = isolated_warehouse()
    assert load_demo(silver) == 16

    async def execute(query, **parameters):
        return [json.loads(line) for line in silver.execute(query, **parameters).splitlines()]

    monkeypatch.setattr(spending, "dashboard_query", execute)
    with TestClient(app) as client:
        response = client.get("/api/spending")
        assert response.status_code == 200
        page = response.json()
        assert page["selected"]["label"] == "Synthetic demo"
        assert page["selected"]["is_demo"] is True
        net = next(row for row in page["totals"] if row["bucket"] is None)
        assert Decimal(net["total"]) == Decimal("257.03")
        assert len(page["expenses"]) == 8
        eligible = next(row for row in page["expenses"] if row["merchant"] == "Corner Bookshop")
        classified = next(row for row in page["expenses"] if row["merchant"] == "West Market")

        async def suggest(_client, merchants):
            assert merchants == ["Corner Bookshop"]
            return ["Shopping"]

        monkeypatch.setattr(spending.classifier, "suggest", suggest)
        suggestion_request = {
            "item": page["selected"]["id"],
            "transactions": [eligible["id"], classified["id"]],
        }
        assert client.post("/api/spending/suggestions", json=suggestion_request).status_code == 403
        suggested = client.post(
            "/api/spending/suggestions",
            headers={"Origin": "http://127.0.0.1:8080"},
            json=suggestion_request,
        )
        assert suggested.status_code == 200
        assert suggested.json() == {"suggestions": [{"id": eligible["id"], "category": "Shopping"}]}
        assert client.get("/api/spending").json() == page
        assert [row["merchant"] for row in page["reviews"]] == ["Harbor Books"]
        assert [row["operation"] for row in page["reviews"]] == ["PIX"]
        assert "Card statement" not in {row["merchant"] for row in page["expenses"]}
        assert (
            next(row for row in page["expenses"] if row["merchant"] == "Museum Studio")["status"]
            == "PENDING"
        )
        row = next(row for row in page["expenses"] if row["merchant"] == "West Market")
        response = client.post(
            "/api/spending/rules",
            headers={"Origin": "http://127.0.0.1:8080"},
            json={"item": page["selected"]["id"], "transaction": row["id"], "category": "Home"},
        )
        assert response.status_code == 204
        updated = client.get("/api/spending").json()
        assert {
            row["category"] for row in updated["expenses"] if row["merchant"] == "West Market"
        } == {"Home"}
        assert load_demo(silver) == 16
        assert client.get("/api/spending").json() == updated
        review = page["reviews"][0]
        request = {"item": page["selected"]["id"], "transaction": review["id"]}
        headers = {"Origin": "http://127.0.0.1:8080"}
        wrong_item = "10000000-0000-4000-8000-100000000002"
        assert (
            client.post(
                "/api/spending/reviews",
                headers=headers,
                json={**request, "item": wrong_item, "decision": "include"},
            ).status_code
            == 404
        )
        for decision, expected in (
            ("include", "280.53"),
            ("include", "280.53"),
            ("exclude", "257.03"),
            ("reset", "257.03"),
        ):
            assert (
                client.post(
                    "/api/spending/reviews", headers=headers, json={**request, "decision": decision}
                ).status_code
                == 204
            )
            assert load_demo(silver) == 16
            report = client.get("/api/spending").json()
            net = next(row for row in report["totals"] if row["bucket"] is None)
            assert Decimal(net["total"]) == Decimal(expected)
            assert report["reviews"][0]["decision"] == ("" if decision == "reset" else decision)


def test_investment_details_and_movement_costs_reach_silver():
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from finance_ingestion.silver import normalized_row
    from finance_lake.bronze import ReplayRecord

    manifest = SimpleNamespace(run_id=uuid4(), retrieved_at_utc=datetime(2026, 1, 2, tzinfo=UTC))

    def row(resource, record):
        entry = ReplayRecord(uuid4(), uuid4(), uuid4(), {"id": str(uuid4()), **record}, resource)
        return normalized_row(manifest, uuid4(), entry, 0, set())

    position = row(
        "investments",
        {
            "name": "LCA Banco X",
            "issuer": "Banco X",
            "purchaseDate": "2025-01-10",
            "fixedAnnualRate": Decimal("6.5"),
            "amountOriginal": 1000,
            "amountWithdrawal": 1080,
            "taxes": 12,
            "taxes2": 0,
        },
    )
    assert (position["name"], position["purchase_date"]) == ("LCA Banco X", "2025-01-10")
    assert Decimal(position["original_amount"]) == 1000
    assert Decimal(position["income_tax"]) == 12 and Decimal(position["iof"]) == 0
    movement = row(
        "investment_movements",
        {
            "movementType": "DEBIT",
            "netAmount": 98,
            "expenses": {
                "brokerageFee": Decimal("1.5"),
                "custodyFee": Decimal("0.5"),
                "incomeTax": 3,
            },
        },
    )
    assert movement["movement_type"] == "DEBIT"
    assert Decimal(movement["fees"]) == 2 and Decimal(movement["income_tax"]) == 3
    assert row("investment_movements", {})["fees"] is None
