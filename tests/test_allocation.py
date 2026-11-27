from fastapi.testclient import TestClient
from finance_api import investments
from finance_api.investment_history import CDI, ETF_STOCKS
from finance_api.main import app

HEADERS = {"Origin": "http://127.0.0.1:8080", "Content-Type": "application/json"}
OTHER = "11111111-1111-1111-1111-111111111111"


def fake(monkeypatch, targets=()):
    queries = []

    async def query(sql, **parameters):
        queries.append((sql, parameters))
        if "FROM analytics.investment_classes" in sql:
            return [{"id": CDI, "name": "CDI"}, {"id": ETF_STOCKS, "name": "Stocks"}]
        if "investment_class_targets" in sql and sql.startswith("SELECT"):
            return list(targets)
        if "investment_class_assignments" in sql:
            return [{"position": "p3", "class": ETF_STOCKS}]
        if "investment_position_history" in sql:
            return [
                {"position": "p1", "type": "SAVINGS_BOX", "currency": "BRL", "balance": "100.5"},
                {
                    "position": "p2",
                    "type": "FIXED_INCOME",
                    "indexer": "CDI",
                    "currency": "BRL",
                    "balance": "50",
                },
                {"position": "p3", "type": "FIXED_INCOME", "currency": "BRL", "balance": "25"},
                {"position": "p4", "type": "OTHER", "currency": "BRL", "balance": "10"},
            ]
        if "accounts_dashboard" in sql:
            return [{"currency": "BRL", "total": "300"}]
        return []

    monkeypatch.setattr(investments, "dashboard_query", query)
    return queries


def test_allocation_groups_positions_by_class_and_reports_bank_cash(monkeypatch):
    fake(monkeypatch, [{"id": CDI, "percent": "60.0000"}])
    with TestClient(app) as client:
        body = client.get("/api/investments/allocation").json()
    assert body["classes"] == [
        {"id": CDI, "name": "CDI", "target": "60.0000"},
        {"id": ETF_STOCKS, "name": "Stocks", "target": "0"},
    ]
    held = {row["class_id"]: row["total"] for row in body["held"]}
    # The chosen class wins over the automatic one; positions without one stay apart.
    assert held == {CDI: "150.5", ETF_STOCKS: "25", "": "10"}
    assert body["cash"] == [{"currency": "BRL", "total": "300"}]


def test_targets_must_add_up_to_100_and_name_active_classes(monkeypatch):
    queries = fake(monkeypatch, [{"id": CDI, "percent": "60.0000"}])
    with TestClient(app) as client:
        put = client.put
        path = "/api/investments/targets"
        assert put(path, json={"targets": {CDI: 50}}).status_code == 403
        assert put(path, json={"targets": {CDI: 50}}, headers=HEADERS).status_code == 422
        assert put(path, json={"targets": {CDI: 101}}, headers=HEADERS).status_code == 422
        assert put(path, json={"targets": {OTHER: 100}}, headers=HEADERS).status_code == 404
        assert not [sql for sql, _ in queries if sql.startswith("INSERT")]
        saved = put(path, json={"targets": {CDI: 60, ETF_STOCKS: 40}}, headers=HEADERS)
    assert saved.status_code == 204
    inserts = [parameters for sql, parameters in queries if sql.startswith("INSERT")]
    # Only the class whose target changed is written.
    assert inserts == [{"ids": f"['{ETF_STOCKS}']", "percents": "[40]"}]


def test_clearing_every_target_is_allowed(monkeypatch):
    queries = fake(monkeypatch, [{"id": CDI, "percent": "60.0000"}])
    with TestClient(app) as client:
        response = client.put("/api/investments/targets", json={"targets": {}}, headers=HEADERS)
    assert response.status_code == 204
    inserts = [parameters for sql, parameters in queries if sql.startswith("INSERT")]
    assert inserts == [{"ids": f"['{CDI}']", "percents": "[0]"}]
