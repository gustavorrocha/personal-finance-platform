import json
from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from finance_api import accounts
from finance_api.main import app
from finance_ingestion.collection import collect, entity_key, item_key
from finance_ingestion.spending_demo import load_account_demo, load_demo
from finance_lake.bronze import CapturePage
from finance_lake.manifest import json_bytes

from tests.test_provider_ingestion import CARD, ITEM, NEW_ITEM, WHEN
from tests.test_provider_ingestion import isolated_warehouse as isolated_warehouse
from tests.test_provider_ingestion import pipeline as pipeline


def test_account_snapshot_is_read_only_and_validates_scope():
    with TestClient(app) as client:
        assert client.post("/api/accounts", json={}).status_code == 405
        assert client.get("/api/accounts", headers={"Host": "outside.test"}).status_code == 400
        response = client.get("/api/accounts", params={"item": "private-invalid-value"})
        assert response.status_code == 422
        assert response.json() == {"detail": "Invalid request"}


def test_account_history_requires_scope_and_bounds_limit():
    path = "/api/accounts/history"
    scope = {"item": str(uuid4()), "account": str(uuid4())}
    with TestClient(app) as client:
        assert client.post(path).status_code == 405
        assert client.get(path, headers={"Host": "outside.test"}).status_code == 400
        assert client.get(path, params={"item": scope["item"]}).status_code == 422
        for invalid in ({"account": "private-value"}, {"limit": 0}, {"limit": 201}):
            response = client.get(path, params={**scope, **invalid})
            assert response.status_code == 422
            assert response.json() == {"detail": "Invalid request"}


def test_account_history_keeps_published_observations_separate(isolated_warehouse, monkeypatch):
    silver = isolated_warehouse()

    def observe(source, offset, balance):
        record = {"id": CARD, "type": "CREDIT", "balance": balance, "currencyCode": "BRL"}
        manifest = silver.lake.commit(
            run_id=uuid4(),
            retrieved_at=WHEN + timedelta(days=offset),
            item_alias=f"item-{item_key(source).hex}",
            capture_kind="full",
            payloads=[
                CapturePage(
                    "items",
                    json_bytes({"id": source, "status": "UPDATED", "connector": {"id": 123}}),
                ),
                CapturePage("accounts", json_bytes({"results": [record]})),
            ],
        )
        silver.replay(manifest.run_id)

    observe(ITEM, 0, 42.25)
    observe(ITEM, 0, 42.25)
    observe(ITEM, 1, 0)
    observe(ITEM, 2, None)
    observe(NEW_ITEM, 1, 95)
    silver.execute(
        "INSERT INTO core.provider_versions SELECT * REPLACE "
        "(generateUUIDv4() AS run_id, observed_at + INTERVAL 5 DAY AS observed_at) "
        "FROM core.provider_versions "
        "WHERE resource = 'accounts' AND item_key = {item:UUID} LIMIT 1",
        item=str(item_key(ITEM)),
    )

    async def query(sql, **parameters):
        return [json.loads(line) for line in silver.execute(sql, **parameters).splitlines()]

    monkeypatch.setattr(accounts, "dashboard_query", query)
    path = "/api/accounts/history"
    item = item_key(ITEM)
    other = item_key(NEW_ITEM)
    scope = {"item": str(item), "account": str(entity_key(item, "accounts", CARD))}
    other_scope = {"item": str(other), "account": str(entity_key(other, "accounts", CARD))}
    with TestClient(app) as client:
        response = client.get(path, params=scope)
        assert response.status_code == 200
        history = response.json()
        assert not history["truncated"]
        assert history["observations"] == [
            {"observed_at": "2024-11-12T12:00:00.000000Z", "currency": "BRL", "balance": None},
            {"observed_at": "2024-11-11T12:00:00.000000Z", "currency": "BRL", "balance": "0"},
            {"observed_at": "2024-11-10T12:00:00.000000Z", "currency": "BRL", "balance": "42.25"},
        ]
        limited = client.get(path, params={**scope, "limit": 2}).json()
        assert limited == {"observations": history["observations"][:2], "truncated": True}
        assert client.get(path, params={**scope, "item": str(other)}).status_code == 404
        assert client.get(path, params=other_scope).json()["observations"][0]["balance"] == "95"


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

        assert load_demo(silver) == 16
        for _ in range(2):
            assert load_account_demo(silver) == 7
        report = client.get("/api/accounts").json()
        demo = next(connection for connection in report["connections"] if connection["is_demo"])
        preview = client.get("/api/accounts", params={"item": demo["id"]}).json()
        assert {(row["currency"], row["balance"]) for row in preview["accounts"]} == {
            ("BRL", "1850.75"),
            ("BRL", "-320.4"),
            ("USD", None),
        }
