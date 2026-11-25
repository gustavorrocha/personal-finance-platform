import json
from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from finance_api import investments, spending
from finance_api.main import app
from finance_ingestion.collection import item_key
from finance_lake.bronze import CapturePage
from finance_lake.manifest import json_bytes

from tests.test_provider_ingestion import INVESTMENT, ITEM, NEW_ITEM, WHEN
from tests.test_provider_ingestion import isolated_warehouse as isolated_warehouse
from tests.test_provider_ingestion import pipeline as pipeline


def test_investment_snapshot_is_read_only_and_validates_scope():
    with TestClient(app) as client:
        assert client.post("/api/investments", json={}).status_code == 405
        assert client.get("/api/investments", headers={"Host": "outside.test"}).status_code == 400
        assert client.get("/api/investments", params={"item": "invalid"}).status_code == 422


def test_investments_remain_separate_and_preserve_latest_reported_values(
    isolated_warehouse, monkeypatch
):
    silver = isolated_warehouse()
    second = str(uuid4())
    private_code = "12345678000199"
    record = {
        "id": INVESTMENT,
        "code": "ABCD11",
        "type": "EQUITY",
        "currencyCode": "BRL",
        "date": "2024-11-09",
        "amount": 100,
        "balance": 96.25,
        "quantity": 4,
        "value": 25,
    }

    def observe(source, time, positions):
        manifest = silver.lake.commit(
            run_id=uuid4(),
            retrieved_at=time,
            item_alias=f"item-{item_key(source).hex}",
            capture_kind="full",
            payloads=[
                CapturePage(
                    "items",
                    json_bytes(
                        {
                            "id": source,
                            "status": "UPDATED",
                            "connector": {"id": 123},
                        }
                    ),
                ),
                CapturePage("investments", json_bytes({"results": positions})),
            ],
        )
        silver.replay(manifest.run_id)

    observe(
        ITEM,
        WHEN,
        [
            record,
            {**record, "id": second},
            {
                "id": str(uuid4()),
                "code": private_code,
                "type": "MUTUAL_FUND",
                "amount": 500,
            },
        ],
    )
    observe(ITEM, WHEN + timedelta(days=1), [{**record, "balance": 98.75}])
    observe(NEW_ITEM, WHEN, [record])

    async def query(sql, **parameters):
        return [json.loads(line) for line in silver.execute(sql, **parameters).splitlines()]

    monkeypatch.setattr(investments, "dashboard_query", query)
    monkeypatch.setattr(spending, "dashboard_query", query)
    with TestClient(app) as client:
        assert client.get("/api/investments").json()["positions"] == []
        response = client.get("/api/investments", params={"item": str(item_key(ITEM))})
        assert response.status_code == 200
        assert private_code not in response.text
        rows = response.json()["positions"]
        assert len(rows) == 3
        tickers = [row for row in rows if row["ticker"] == "ABCD11"]
        assert len({row["id"] for row in tickers}) == 2
        latest = next(row for row in tickers if row["net_balance"] == "98.75")
        assert latest["gross_amount"] == "100"
        assert latest["quantity"] == "4" and latest["unit_price"] == "25"
        assert latest["reference_date"] == "2024-11-09"
        assert latest["observed_at"] == "2024-11-11T12:00:00.000000Z"
        assert next(row for row in rows if row["ticker"] is None)["net_balance"] is None
        other = client.get("/api/investments", params={"item": str(item_key(NEW_ITEM))}).json()
        assert len(other["positions"]) == 1 and other["positions"][0]["net_balance"] == "96.25"
        assert other["positions"][0]["id"] != latest["id"]
