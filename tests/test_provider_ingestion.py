import gzip
import os
import time
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from finance_ingestion import cli
from finance_ingestion.cli import apply_deletions
from finance_ingestion.collection import collect, entity_key, item_key
from finance_ingestion.silver import SilverWarehouse
from finance_ingestion.warehouse import BronzeWarehouse
from finance_lake import LocalObjectStore
from finance_lake.bronze import BronzeLake
from finance_lake.manifest import json_bytes
from finance_pluggy.client import Pluggy, Unavailable

from scripts.phase0 import COMPOSE, ROOT, command, sql

ITEM = "10000000-0000-4000-8000-000000000001"
NEW_ITEM = "10000000-0000-4000-8000-000000000002"
CARD = "10000000-0000-4000-8000-000000000003"
TX = "10000000-0000-4000-8000-000000000004"
BILL = "10000000-0000-4000-8000-000000000005"
INVESTMENT = "10000000-0000-4000-8000-000000000006"
MOVEMENT = "10000000-0000-4000-8000-000000000007"
LATE_TX = "10000000-0000-4000-8000-000000000008"
EVENT = "10000000-0000-4000-8000-000000000009"
WHEN = datetime(2024, 11, 10, 12, tzinfo=UTC)


class Provider:
    status = "UPDATED"
    transaction_status = "PENDING"
    fail_page = False
    backdated = False

    def __init__(self):
        self.filters = []
        self.item_raw = None

    def respond(self, request):
        path = request.url.path
        params = request.url.params
        if path == "/auth":
            return httpx.Response(200, json={"apiKey": "synthetic-key"})
        if path in (f"/items/{ITEM}", f"/items/{NEW_ITEM}"):
            self.item_raw = (
                b"  "
                + json_bytes(
                    {
                        "id": path.rsplit("/", 1)[1],
                        "status": self.status,
                        "connector": {
                            "id": 123,
                            "products": [
                                "ACCOUNTS",
                                "CREDIT_CARDS",
                                "TRANSACTIONS",
                                "INVESTMENTS",
                                "INVESTMENTS_TRANSACTIONS",
                            ],
                        },
                    }
                )
                + b"\n"
            )
            return httpx.Response(200, content=self.item_raw)
        if path == "/v2/transactions":
            assert params["accountId"] == CARD
            self.filters.append(dict(params))
            if "after" in params and self.fail_page:
                return httpx.Response(422, text="sensitive response body")
            row = {
                "id": TX,
                "accountId": CARD,
                "status": self.transaction_status,
                "amount": -10.125,
                "currencyCode": "BRL",
                "date": "2024-11-08",
                "description": "synthetic private description",
            }
            if "createdAtFrom" in params:
                rows = [{**row, "id": LATE_TX, "date": "2024-01-01"}] if self.backdated else []
                return httpx.Response(200, json={"results": rows, "next": None})
            if "after" in params:
                return httpx.Response(200, json={"results": [row], "next": None})
            return httpx.Response(
                200,
                json={
                    "results": [row],
                    "next": f"?accountId={CARD}&after=opaque%2Bcursor",
                },
            )
        rows = {
            f"/items/{ITEM}/resources": [
                {
                    "resourceId": "opaque-resource-1",
                    "type": "ACCOUNT",
                    "status": "AVAILABLE",
                }
            ],
            f"/items/{NEW_ITEM}/resources": [],
            "/accounts": [{"id": CARD, "type": "CREDIT", "balance": 42, "currencyCode": "BRL"}],
            "/bills": [
                {
                    "id": BILL,
                    "dueDate": "2024-11-20",
                    "totalAmount": 10.125,
                    "totalAmountCurrencyCode": "BRL",
                }
            ],
            "/investments": [
                {
                    "id": INVESTMENT,
                    "amount": 100,
                    "quantity": 4,
                    "value": 25,
                    "type": "FIXED_INCOME",
                    "date": "2024-11-09",
                }
            ],
            f"/investments/{INVESTMENT}/transactions": [
                {
                    "id": MOVEMENT,
                    "amount": 100,
                    "type": "BUY",
                    "date": "2024-10-31",
                }
            ],
        }[path]
        assert params["page"] == "1"
        return httpx.Response(200, json={"results": rows, "page": 1, "totalPages": 1})


@pytest.fixture
def pipeline(tmp_path):
    provider = Provider()
    lake = BronzeLake(LocalObjectStore(tmp_path / "lake"))
    with httpx.Client(transport=httpx.MockTransport(provider.respond)) as http:
        client = Pluggy(http, max_pages=10)
        client.authenticate("client", "secret")
        yield provider, lake, client


def test_capture_preserves_original_responses_and_existing_account_windows(pipeline):
    provider, lake, client = pipeline
    item = item_key(ITEM)
    account = entity_key(item, "accounts", CARD)
    manifest = collect(client, lake, ITEM, uuid4(), WHEN, (WHEN, {account}))
    assert manifest.capture_kind == "incremental"
    assert manifest.manifest_version == 2
    assert gzip.decompress(lake.store.get(manifest.objects[0].object_key)) == provider.item_raw
    assert manifest.item_alias == f"item-{item.hex}"
    assert ITEM.encode() not in manifest.to_bytes()
    assert CARD.encode() not in manifest.to_bytes()
    assert "createdAtFrom" in provider.filters[0]
    assert "dateFrom" in provider.filters[1]
    assert provider.filters[2]["after"] == "opaque+cursor"
    provider.filters.clear()
    # The prior checkpoint cannot limit collection for a newly discovered account.
    collect(client, lake, ITEM, uuid4(), WHEN, (WHEN, set()))
    assert provider.filters[0] == {"accountId": CARD}


def test_failed_page_does_not_commit_a_capture(pipeline):
    provider, lake, client = pipeline
    provider.fail_page = True
    with pytest.raises(Unavailable, match="could not be read"):
        collect(client, lake, ITEM, uuid4(), WHEN, None)
    assert not lake.list_runs()


def test_cli_records_failed_run_without_checkpoint_or_provider_details(
    pipeline, monkeypatch, capsys
):
    provider, lake, client = pipeline
    provider.fail_page = True
    queries = []
    monkeypatch.setattr(cli, "configured_client", lambda **kwargs: nullcontext((client, [ITEM])))
    monkeypatch.setattr(
        cli, "docker_sql", lambda query, native=b"": queries.append((query, native)) or b""
    )
    assert cli.main(["--root", str(lake.store.root), "sync", "--full"]) == 1
    output = capsys.readouterr()
    assert '"status": "failed"' in output.out
    assert ITEM not in output.out + output.err
    assert "sensitive response body" not in output.out + output.err
    assert not lake.list_runs()
    assert len(list(lake.store.root.glob("failures/*/status.json"))) == 1
    assert b"capture_failed" in queries[-1][1]
    assert all("ingestion_publications" not in query for query, _ in queries)


def test_provider_stage_has_no_publication_after_failed_silver_write(pipeline):
    _, lake, client = pipeline
    manifest = collect(client, lake, ITEM, uuid4(), WHEN, None)
    writes = []

    def execute(query, native=b""):
        writes.append(query)
        if query.startswith("INSERT INTO core.provider_versions"):
            raise RuntimeError("synthetic stage failure")
        return b""

    silver = SilverWarehouse(BronzeWarehouse(lake, execute), execute)
    with pytest.raises(RuntimeError, match="stage failure"):
        silver.replay(manifest.run_id)
    assert not any("ingestion_publications" in query for query in writes)
    assert lake.verify_run(manifest.run_id) == manifest


@pytest.fixture
def isolated_warehouse(pipeline):
    if os.environ.get("FINANCE_TEST_CLICKHOUSE") != "1":
        pytest.skip("Set FINANCE_TEST_CLICKHOUSE=1 to use disposable ClickHouse")
    _, lake, _ = pipeline
    names = []

    def start():
        name = f"finance-silver-test-{uuid4().hex}"
        command(COMPOSE + ["run", "--rm", "--no-deps", "-d", "--name", name, "restore"])
        names.append(name)

        def execute(query, native=b"", **parameters):
            return sql(query, container=name, native=native, parameters=parameters)

        for _ in range(40):
            try:
                execute("SELECT 1")
                break
            except RuntimeError:
                time.sleep(0.5)
        else:
            raise RuntimeError("Disposable ClickHouse did not start")
        for migration in sorted((ROOT / "infra/migrations").glob("*.sql")):
            execute(migration.read_text(encoding="utf-8"))
        return SilverWarehouse(BronzeWarehouse(lake, execute), execute)

    try:
        yield start
    finally:
        for name in names:
            command(["docker", "rm", "-f", name])


def test_silver_current_checkpoints_tombstones_and_offline_rebuild(
    pipeline, isolated_warehouse, monkeypatch
):
    provider, lake, client = pipeline
    silver = isolated_warehouse()
    item = item_key(ITEM)
    account = entity_key(item, "accounts", CARD)

    def observe(offset, item_id=ITEM):
        manifest = collect(
            client,
            lake,
            item_id,
            uuid4(),
            WHEN + timedelta(days=offset),
            silver.checkpoint(item_key(item_id)),
        )
        silver.replay(manifest.run_id)
        return manifest

    def totals(warehouse):
        return warehouse.execute(
            "SELECT count(), sum(amount) FROM core.bank_transaction_current FORMAT TSV"
        ).strip()

    first = collect(client, lake, ITEM, uuid4(), WHEN, None)

    def fail_before_publication(query, native=b""):
        if query.startswith("INSERT INTO metadata.ingestion_publications"):
            raise RuntimeError("synthetic publication failure")
        return silver.execute(query, native)

    with pytest.raises(RuntimeError, match="publication failure"):
        SilverWarehouse(silver.bronze, fail_before_publication).replay(first.run_id)
    assert silver.checkpoint(item) is None
    assert silver.execute("SELECT count() FROM core.bank_transaction_current").strip() == b"0"
    assert int(silver.execute("SELECT count() FROM core.provider_versions")) > 0
    silver.replay(first.run_id)
    assert totals(silver) == b"1\t-10.125"
    assert silver.execute("SELECT count() FROM metadata.bronze_objects_current").strip() == b"0"
    assert int(silver.execute("SELECT count() FROM metadata.provider_bronze_objects_current")) > 0
    assert silver.checkpoint(item) == (WHEN, {account})
    assert (
        silver.execute("SELECT status FROM core.bank_transaction_current FORMAT TSV").strip()
        == b"PENDING"
    )
    assert (
        silver.execute("SELECT sum(amount) FROM core.credit_card_bill_current").strip() == b"10.125"
    )
    assert silver.execute("SELECT sum(unit_value) FROM core.instrument_current").strip() == b"25"
    assert silver.execute("SELECT count() FROM core.investment_movement_current").strip() == b"1"
    provider.fail_page = True
    with pytest.raises(Unavailable):
        observe(1)
    assert silver.checkpoint(item) == (WHEN, {account})
    provider.fail_page = False
    provider.status = "WAITING_USER_INPUT"
    assert observe(1).capture_kind == "pending"
    assert (
        silver.execute("SELECT status FROM core.connection_current").strip()
        == b"WAITING_USER_INPUT"
    )
    assert silver.checkpoint(item) == (WHEN, {account})
    provider.status = "UPDATED"
    provider.transaction_status = "POSTED"
    provider.backdated = True
    second = observe(2)
    assert second.capture_kind == "incremental"
    assert totals(silver) == b"2\t-20.25"
    assert (
        silver.execute("SELECT uniqExact(status) FROM core.bank_transaction_current").strip()
        == b"1"
    )
    observe(3)
    silver.replay(first.run_id)
    silver.replay(second.run_id)
    assert totals(silver) == b"2\t-20.25"
    assert (
        silver.execute(
            "SELECT distinct status FROM core.bank_transaction_current FORMAT TSV"
        ).strip()
        == b"POSTED"
    )
    assert silver.checkpoint(item) == (WHEN + timedelta(days=3), {account})
    deletion = json_bytes(
        {
            "event": "transactions/deleted",
            "eventId": EVENT,
            "itemId": ITEM,
            "accountId": CARD,
            "transactionIds": [TX],
        }
    )
    for _ in range(2):
        assert apply_deletions(silver, deletion, WHEN + timedelta(days=4)) == 1
    assert totals(silver) == b"1\t-10.125"
    assert silver.checkpoint(item) == (WHEN + timedelta(days=3), {account})
    assert observe(5, NEW_ITEM).capture_kind == "full"
    assert totals(silver) == b"2\t-20.25"
    assert silver.execute("SELECT count() FROM core.credit_card_current").strip() == b"2"
    observe(6)
    assert totals(silver) == b"3\t-30.375"

    restored = isolated_warehouse()
    monkeypatch.setattr(cli, "docker_sql", restored.execute)
    arguments = ["--root", str(lake.store.root)]
    assert cli.main([*arguments, "rebuild-warehouse", "--from-bronze"]) == 0
    assert cli.main([*arguments, "replay", "--run-id", str(first.run_id)]) == 0
    assert restored.checkpoint(item) == silver.checkpoint(item)
    assert totals(restored) == totals(silver)
    current = "SELECT * FROM core.bank_transaction_current ORDER BY entity_key FORMAT TSV"
    assert restored.execute(current) == silver.execute(current)
