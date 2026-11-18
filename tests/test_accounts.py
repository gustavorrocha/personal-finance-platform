import json
from uuid import uuid4

from fastapi.testclient import TestClient
from finance_api import accounts
from finance_api.main import app
from finance_ingestion.collection import collect

from tests.test_provider_ingestion import ITEM, NEW_ITEM, WHEN
from tests.test_provider_ingestion import isolated_warehouse as isolated_warehouse
from tests.test_provider_ingestion import pipeline as pipeline


def test_account_snapshot_is_read_only_and_validates_scope():
    with TestClient(app) as client:
        assert client.post("/api/accounts", json={}).status_code == 405
        assert client.get("/api/accounts", headers={"Host": "outside.test"}).status_code == 400
        response = client.get("/api/accounts", params={"item": "private-invalid-value"})
        assert response.status_code == 422
        assert response.json() == {"detail": "Invalid request"}


def test_account_snapshot_scopes_distinct_connections_and_keeps_reported_values(
    pipeline, isolated_warehouse, monkeypatch
):
    _, lake, provider = pipeline
    silver = isolated_warehouse()
    for item in (ITEM, NEW_ITEM):
        manifest = collect(provider, lake, item, uuid4(), WHEN, None)
        silver.replay(manifest.run_id)

    async def query(sql, **parameters):
        return [json.loads(line) for line in silver.execute(sql, **parameters).splitlines()]

    monkeypatch.setattr(accounts, "dashboard_query", query)
    with TestClient(app) as client:
        response = client.get("/api/accounts")
        assert response.status_code == 200
        summary = response.json()
        assert len(summary["connections"]) == 2
        assert summary["selected"] is None and summary["accounts"] == []
        account_ids = set()
        for connection in summary["connections"]:
            snapshot = client.get("/api/accounts", params={"item": connection["id"]}).json()
            assert snapshot["selected"] == connection
            assert len(snapshot["accounts"]) == 1
            row = snapshot["accounts"][0]
            assert row["type"] == "CREDIT"
            assert row["balance"] == "42" and row["currency"] == "BRL"
            assert row["observed_at"] == "2024-11-10T12:00:00.000000Z"
            account_ids.add(row["id"])
        assert len(account_ids) == 2
        assert client.get("/api/accounts", params={"item": str(uuid4())}).status_code == 404
