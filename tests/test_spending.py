import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from finance_api import spending
from finance_api.main import app
from finance_ingestion.spending import spending_fields
from finance_ingestion.spending_demo import load_demo

from tests.test_provider_ingestion import isolated_warehouse as isolated_warehouse
from tests.test_provider_ingestion import pipeline as pipeline


def test_spending_requires_purchase_evidence_and_excludes_transfers_and_settlements():
    debit = {"type": "DEBIT", "description": "Synthetic Market"}
    assert spending_fields(debit, "tx")["spending_kind"] == ""
    card = {**debit, "creditCardMetadata": {}, "category": "Groceries"}
    assert spending_fields(card, "tx")["spending_kind"] == "purchase"
    assert spending_fields(card, "tx")["spending_category"] == "Groceries"
    for operation in ("PIX", "TED", "PAGAMENTO_FATURA"):
        assert spending_fields({**card, "operationType": operation}, "tx")["spending_kind"] == ""
    refund = {**card, "type": "CREDIT", "operationType": "ESTORNO"}
    assert spending_fields(refund, "tx")["spending_kind"] == "refund"
    assert (
        spending_fields(refund, "tx")["merchant_key"] == spending_fields(card, "tx")["merchant_key"]
    )
    assert "Synthetic Market" not in str(spending_fields(card, "tx"))
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


def test_dashboard_excludes_nonexpenses_and_rules_survive_replay(isolated_warehouse, monkeypatch):
    silver = isolated_warehouse()
    assert load_demo(silver) == 11

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
        assert len(page["expenses"]) == 7
        assert {row["merchant"] for row in page["expenses"]}.isdisjoint(
            {"Museum Studio", "Card statement"}
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
        assert load_demo(silver) == 11
        assert client.get("/api/spending").json() == updated
