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
        ({"type": "DEBIT", "description": "COMPRA DE TESOURO DIRETO: IPCA+ 2035"}, "contribution"),
        ({"type": "DEBIT", "description": "EMISSAO - LCA BANCO X"}, "contribution"),
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
        transfer = {**debit, "operationType": operation, "category": "Transfer - PIX"}
        assert spending_fields(transfer, "tx")["spending_kind"] == "review"
        own = {**transfer, "category": "Same person transfer"}
        assert spending_fields(own, "tx")["spending_kind"] == ""
        utility = {**debit, "operationType": operation, "categoryId": "17020002"}
        assert spending_fields(utility, "tx")["spending_kind"] == "purchase"
        boleto = {**utility, "categoryId": "05000000", "category": "Transfers"}
        assert spending_fields(boleto, "tx")["spending_kind"] == "review"
    for description in ("Pagamento de fatura", "Pagamento cartão de crédito"):
        bill = {"type": "DEBIT", "description": description, "categoryId": "05000000"}
        assert spending_fields(bill, "tx")["spending_kind"] == ""
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
        "category": "10000000-0000-4000-8000-100000000003",
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
    async def connections(query):
        if "connection_names" in query:
            return []
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
        "categoryId": "08080000",
    }
    observe(
        NEW_ITEM,
        "CREDIT",
        [
            {"amount": 25, "operationType": "PAGAMENTO", "creditCardMetadata": {}},
            # Outside the charted window: rule precedence only.
            *(
                {
                    "amount": amount,
                    "date": "2023-01-10",
                    "descriptionRaw": label,
                    "categoryId": provider,
                    "creditCardMetadata": {"payeeMCC": 5812},
                }
                for label, amount, provider in (
                    ("Broad provider", 3, "10000000"),
                    ("Specific provider", 4, "11020000"),
                    ("Unmapped provider", 5, "55550000"),
                )
            ),
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
        assert page["chart_month"] == "2024-11"
        october = client.get(path, params={"item": "all", "month": "2024-10"}).json()
        assert october["month"] == "2024-10" and october["chart_month"] == "2024-11"
        assert {row["month"] for row in october["history"]} >= {"2024-10", "2024-11"}
        old = client.get(path, params={"item": "all", "month": "2023-01"}).json()
        assert old["chart_month"] == "2023-01"
        assert {row["month"] for row in old["history"]} <= {"2022-12", "2023-01"} | {
            f"2022-{index:02d}" for index in range(1, 13)
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
        precedence = execute_sql(
            "SELECT description, category_rule, category, subcategory "
            "FROM analytics.spending_dashboard WHERE economic_date = '2023-01-10' "
            "ORDER BY description FORMAT TSV"
        )
        assert precedence.splitlines() == [
            "Broad provider	mcc	Alimentação	Restaurantes e bares",
            "Specific provider	provider	Alimentação	Delivery",
            "Unmapped provider	mcc	Alimentação	Restaurantes e bares",
        ]
        positions = client.get("/api/investments", params={"item": str(item_key(ITEM))}).json()
        assert {row["name"] for row in positions["positions"]} == {
            "Casa",
            "Dolares",
            "Reserva",
            "Viagem",
        }
        assert {row["category"] for row in page["history"] if row["status"] == "PENDING"} == {
            "Compras"
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
        assert purchase["category"] == "Compras" and purchase["category_rule"] == "provider"
        assert purchase["bank_category"] == "Office supplies"
        assert purchase["transaction_time"] == "2024-11-10T16:25:00.000000Z"
        assert (purchase["installment_number"], purchase["total_installments"]) == (2, 4)
        # A pending purchase already counts, so its category can be changed right away.
        assert purchase["provider_category_id"] == "08080000"
        tree = {row["name"]: row["id"] for row in page["categories"]}
        pending_rule = {
            "item": purchase["item"],
            "transaction": purchase["id"],
            "scope": "transaction",
            "category": tree["Presentes"],
        }
        local = {"Origin": "http://127.0.0.1:8080"}
        assert client.post(path + "/rules", headers=local, json=pending_rule).status_code == 204
        relabeled = client.get(path, params={"item": "all", "search": "Loja de teste"}).json()
        assert [(row["subcategory"], row["category_rule"]) for row in relabeled["expenses"]] == [
            ("Presentes", "transaction")
        ]
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

        categories = {row["name"]: row["id"] for row in page["categories"]}
        assert {"Alimentação", "Delivery", "Compras", "Moradia"} <= set(categories)

        async def suggest(_client, merchants, labels):
            assert sorted(merchants) == ["Corner Bookshop", "West Market"]
            assert "Alimentação / Delivery" in labels and "Compras" in labels
            return ["Compras" if merchant == "Corner Bookshop" else None for merchant in merchants]

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
        assert suggested.json() == {
            "suggestions": [
                {"id": eligible["id"], "category": categories["Compras"], "label": "Compras"}
            ]
        }
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
            json={
                "item": page["selected"]["id"],
                "transaction": row["id"],
                "category": categories["Moradia"],
            },
        )
        assert response.status_code == 204
        updated = client.get("/api/spending").json()
        assert {
            (row["category"], row["category_rule"])
            for row in updated["expenses"]
            if row["merchant"] == "West Market"
        } == {("Moradia", "merchant")}
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


def test_merchant_identity_keeps_companies_and_recognizes_own_transfers():
    def pix(kind, value, name):
        return {
            "type": "DEBIT",
            "amount": 10,
            "categoryId": "05070000",
            "paymentData": {
                "paymentMethod": "PIX",
                "receiver": {"name": name, "documentNumber": {"type": kind, "value": value}},
            },
        }

    company = spending_fields(pix("CNPJ", "12.345.678/0001-90", "Padaria X LTDA"), "tx")
    assert company["counterparty_cnpj"] == "12345678000190"
    assert company["merchant_label"] == "Padaria X LTDA"
    assert company["category_id"] == "05070000" and not company["own_transfer"]
    person = pix("CPF", "123.456.789-00", "Private Person")
    fields = spending_fields(person, "tx")
    assert fields["counterparty_type"] == "CPF"
    assert "Private Person" not in str(fields) and "12345678900" not in str(fields)
    own = spending_fields(person, "tx", owners=frozenset({"12345678900"}))
    assert own["own_transfer"] and own["spending_kind"] == ""
    card = {
        "type": "DEBIT",
        "amount": 5,
        "creditCardMetadata": {"payeeMCC": 5812},
        "merchant": {"cnpj": "12345678000190", "cnae": "5611203", "category": "Eating out"},
    }
    fields = spending_fields(card, "tx", card_account=True)
    assert (fields["mcc"], fields["merchant_cnae"]) == (5812, "5611203")
    assert fields["merchant_cnpj"] == "12345678000190"


def test_categories_are_editable_two_level_and_rules_fall_back(isolated_warehouse, monkeypatch):
    silver = isolated_warehouse()
    load_demo(silver)

    async def execute(query, **parameters):
        return [json.loads(line) for line in silver.execute(query, **parameters).splitlines()]

    monkeypatch.setattr(spending, "dashboard_query", execute)
    local = {"Origin": "http://127.0.0.1:8080"}
    with TestClient(app) as client:

        def names():
            return {
                row["name"]: row
                for row in client.get("/api/spending/categories").json()["categories"]
            }

        created = client.post("/api/spending/categories", headers=local, json={"name": " Pets "})
        assert created.status_code == 201
        pets = created.json()["id"]
        food = client.post(
            "/api/spending/categories", headers=local, json={"name": "Ração", "parent": pets}
        ).json()["id"]
        assert names()["Ração"]["parent_id"] == pets and names()["Pets"]["parent_id"] is None
        third_level = {"name": "Seca", "parent": food}
        assert (
            client.post("/api/spending/categories", headers=local, json=third_level).status_code
            == 409
        )
        groceries = names()["Supermercado"]["id"]
        under_child = {"name": "Mercado", "parent": pets}
        assert (
            client.put(
                f"/api/spending/categories/{groceries}", headers=local, json=under_child
            ).status_code
            == 204
        )
        assert names()["Mercado"]["parent_id"] == pets and "Supermercado" not in names()
        moving_parent = {"name": "Pets", "parent": names()["Lazer"]["id"]}
        assert (
            client.put(
                f"/api/spending/categories/{pets}", headers=local, json=moving_parent
            ).status_code
            == 409
        )
        assert client.post("/api/spending/categories", json={"name": "x"}).status_code == 403

        page = client.get("/api/spending").json()
        market = next(row for row in page["expenses"] if row["merchant"] == "West Market")
        rule = {"item": page["selected"]["id"], "transaction": market["id"]}
        assert (
            client.post(
                "/api/spending/rules",
                headers=local,
                json={**rule, "scope": "mcc", "category": food},
            ).status_code
            == 409
        )
        assert (
            client.post(
                "/api/spending/rules", headers=local, json={**rule, "category": food}
            ).status_code
            == 204
        )

        def market_categories():
            return {
                (row["category"], row["subcategory"])
                for row in client.get("/api/spending").json()["expenses"]
                if row["merchant"] == "West Market"
            }

        assert market_categories() == {("Pets", "Ração")}
        json_headers = {**local, "Content-Type": "application/json"}
        assert (
            client.delete(f"/api/spending/categories/{pets}", headers=json_headers).status_code
            == 204
        )
        assert "Pets" not in names() and "Ração" not in names()
        assert market_categories() == {("", "")}


def test_savings_box_outflows_and_recurring_entries_fill_unreported_spending(
    isolated_warehouse, monkeypatch
):
    silver = isolated_warehouse()
    load_demo(silver)
    item = item_key(ITEM)
    account = entity_key(item, "accounts", CARD)
    landlord = "12345678000190"

    def observe(observed, box_balance, transactions):
        bank = {
            "reservedBalances": [
                {
                    "name": "Gastos",
                    "identification": "box-1",
                    "availableAmounts": [{"amount": box_balance, "currencyCode": "BRL"}],
                }
            ]
        }
        record = {"id": CARD, "type": "BANK", "currencyCode": "BRL", "bankData": bank}
        rows = [
            {
                "id": str(uuid4()),
                "accountId": CARD,
                "status": "POSTED",
                "currencyCode": "BRL",
                **row,
            }
            for row in transactions
        ]
        manifest = silver.lake.commit(
            run_id=uuid4(),
            retrieved_at=observed,
            item_alias=f"item-{item.hex}",
            capture_kind="full",
            payloads=[
                CapturePage(
                    "items",
                    json_bytes({"id": ITEM, "status": "UPDATED", "connector": {"id": 123}}),
                ),
                CapturePage("accounts", json_bytes({"results": [record]})),
                CapturePage("transactions", json_bytes({"results": rows}), account),
            ],
        )
        silver.replay(manifest.run_id)

    rent = {
        "type": "DEBIT",
        "amount": 900,
        "date": "2024-10-05",
        "description": "Pagamento de conta Imobiliaria",
        "categoryId": "17000000",
        "paymentData": {
            "paymentMethod": "BOLETO",
            "receiver": {
                "name": "Imobiliaria",
                "documentNumber": {"type": "CNPJ", "value": landlord},
            },
        },
    }
    observe(WHEN, 1000, [rent])
    withdrawal = {
        "type": "CREDIT",
        "amount": 200,
        "date": "2024-11-11",
        "description": "Dinheiro retirado Gastos",
    }
    friend = {
        "type": "CREDIT",
        "date": "2024-11-12",
        "description": "Pix recebido Amigo",
        "operationType": "PIX",
        "categoryId": "05070000",
        "category": "Transfer - PIX",
    }
    refunds = [
        {**friend, "id": str(uuid4()), "amount": 60},
        {**friend, "id": str(uuid4()), "amount": 40},
    ]
    observe(WHEN + timedelta(days=2), 300, [rent, withdrawal, *refunds])

    async def execute(query, **parameters):
        return [json.loads(line) for line in silver.execute(query, **parameters).splitlines()]

    monkeypatch.setattr(spending, "dashboard_query", execute)
    local = {"Origin": "http://127.0.0.1:8080"}
    with TestClient(app) as client:
        page = client.get("/api/spending", params={"item": str(item), "month": "2024-11"}).json()
        outflow = next(row for row in page["reviews"] if row["operation"] == "SAVINGS_BOX")
        assert (outflow["date"], Decimal(outflow["amount"])) == ("2024-11-12", Decimal(500))
        assert outflow["merchant"] == "Gastos" and outflow["decision"] == ""
        include = {"item": str(item), "transaction": outflow["id"], "decision": "include"}
        assert client.post("/api/spending/reviews", headers=local, json=include).status_code == 204

        categories = {row["name"]: row["id"] for row in page["categories"]}
        entry = {
            "item": str(item),
            "description": "Aluguel",
            "amount": "950.00",
            "category": categories["Aluguel e condomínio"],
            "day": 31,
            "start": "2024-09",
            "end": "2024-11",
            "cnpj": landlord,
        }
        assert client.post("/api/spending/manual", json=entry).status_code == 403
        assert (
            client.post(
                "/api/spending/manual", headers=local, json={**entry, "end": "2024-08"}
            ).status_code
            == 422
        )
        created = client.post("/api/spending/manual", headers=local, json=entry)
        assert created.status_code == 201

        def manual_months():
            rows = []
            for month in ("2024-09", "2024-10", "2024-11"):
                report = client.get("/api/spending", params={"item": str(item), "month": month})
                rows += [
                    (row["date"], row["amount"], row["subcategory"], row["category_rule"])
                    for row in report.json()["expenses"]
                    if row["merchant"] == "Aluguel"
                ]
            return rows

        # October already has the reported boleto to the same CNPJ; November has 30 days.
        assert manual_months() == [
            ("2024-09-30", "950", "Aluguel e condomínio", "manual"),
            ("2024-11-30", "950", "Aluguel e condomínio", "manual"),
        ]
        filtered = client.get(
            "/api/spending",
            params={
                "item": str(item),
                "month": "2024-11",
                "category": "Moradia",
                "subcategory": "Aluguel e condomínio",
            },
        ).json()
        assert [row["merchant"] for row in filtered["expenses"]] == ["Aluguel"]
        october = client.get("/api/spending", params={"item": str(item), "month": "2024-10"})
        assert outflow["id"] in {row["id"] for row in october.json()["reviews"]}
        november = client.get("/api/spending", params={"item": str(item), "month": "2024-11"})
        totals = {row["bucket"]: Decimal(row["total"]) for row in november.json()["totals"]}
        assert totals[None] == Decimal(1450)

        # Received transfers count only once marked as refunds, and a category can be
        # set for one transaction without touching others from the same sender.
        november = client.get("/api/spending", params={"item": str(item), "month": "2024-11"})
        receipts = november.json()["receipts"]
        assert sorted(Decimal(row["amount"]) for row in receipts) == [40, 60]
        for receipt in receipts:
            decision = {"item": str(item), "transaction": receipt["id"], "decision": "include"}
            response = client.post("/api/spending/reviews", headers=local, json=decision)
            assert response.status_code == 204
        sixty = next(row for row in receipts if Decimal(row["amount"]) == 60)
        rule = {
            "item": str(item),
            "transaction": sixty["id"],
            "scope": "transaction",
            "category": categories["Restaurantes e bares"],
        }
        assert client.post("/api/spending/rules", headers=local, json=rule).status_code == 204
        november = client.get("/api/spending", params={"item": str(item), "month": "2024-11"})
        refunds_listed = {
            Decimal(row["amount"]): (row["subcategory"], row["category_rule"])
            for row in november.json()["expenses"]
            if row["id"] in {receipt["id"] for receipt in receipts}
        }
        assert refunds_listed == {
            Decimal(-60): ("Restaurantes e bares", "transaction"),
            Decimal(-40): ("", ""),
        }
        totals = {row["bucket"]: Decimal(row["total"]) for row in november.json()["totals"]}
        assert totals[None] == Decimal(1350)
        listed = client.get("/api/spending/manual").json()["entries"]
        assert [(row["description"], row["end"], row["cnpj"]) for row in listed] == [
            ("Aluguel", "2024-11", landlord)
        ]
        json_headers = {**local, "Content-Type": "application/json"}
        identifier = created.json()["id"]
        assert (
            client.delete(f"/api/spending/manual/{identifier}", headers=json_headers).status_code
            == 204
        )
        assert manual_months() == []
        assert client.get("/api/spending/manual").json()["entries"] == []

        # A bill registered as paid from the box explains the drop: no outflow remains.
        paid = {
            **entry,
            "description": "Conta paga pelo cofrinho",
            "amount": "500",
            "day": 11,
            "start": "2024-11",
            "end": "2024-11",
            "cnpj": "",
            "savings_box": "Gastos",
        }
        assert (
            client.post(
                "/api/spending/manual", headers=local, json={**paid, "savings_box": "Nope"}
            ).status_code
            == 404
        )
        assert client.post("/api/spending/manual", headers=local, json=paid).status_code == 201
        report = client.get("/api/spending", params={"item": str(item), "month": "2024-11"}).json()
        assert not [row for row in report["reviews"] if row["operation"] == "SAVINGS_BOX"]
        assert "Conta paga pelo cofrinho" in {row["merchant"] for row in report["expenses"]}


def test_received_transfers_are_refund_candidates_only():
    friend = {
        "type": "CREDIT",
        "amount": 40,
        "operationType": "PIX",
        "categoryId": "05070000",
        "category": "Transfer - PIX",
    }
    assert spending_fields(friend, "tx")["spending_kind"] == "reimbursable"
    own = {**friend, "categoryId": "04000000", "category": "Same person transfer"}
    assert spending_fields(own, "tx")["spending_kind"] == ""
    salary = {**friend, "categoryId": "01000000", "category": "Income"}
    assert spending_fields(salary, "tx")["spending_kind"] == ""
    yield_credit = {**friend, "categoryId": "03060000", "category": "Proceeds"}
    assert spending_fields(yield_credit, "tx")["spending_kind"] == ""


def test_savings_box_outflows_remove_the_cdi_yield_between_balances(
    isolated_warehouse, monkeypatch
):
    silver = isolated_warehouse()
    item = item_key(ITEM)
    silver.execute(
        "INSERT INTO core.market_rates (series, day, value) VALUES "
        + ",".join(f"('CDI', '2024-11-{day:02d}', 0.05)" for day in (7, 8, 11, 12, 13, 14))
    )

    def observe(observed, box_balance, transactions=()):
        box = {
            "name": "Reserva",
            "identification": "box-1",
            "availableAmounts": [
                {
                    "amount": box_balance,
                    "currencyCode": "BRL",
                    "remuneration": {"indexer": "CDI", "postFixedIndexerPercentage": 1},
                }
            ],
        }
        record = {
            "id": CARD,
            "type": "BANK",
            "currencyCode": "BRL",
            "bankData": {"reservedBalances": [box]},
        }
        manifest = silver.lake.commit(
            run_id=uuid4(),
            retrieved_at=observed,
            item_alias=f"item-{item.hex}",
            capture_kind="full",
            payloads=[
                CapturePage(
                    "items",
                    json_bytes({"id": ITEM, "status": "UPDATED", "connector": {"id": 123}}),
                ),
                CapturePage("accounts", json_bytes({"results": [record]})),
                CapturePage(
                    "transactions",
                    json_bytes({"results": list(transactions)}),
                    entity_key(item, "accounts", CARD),
                ),
            ],
        )
        silver.replay(manifest.run_id)

    # Sunday to Wednesday: Monday and Tuesday earn 0.05% each, 100.03 on 100000. The
    # balance rose by 60, so about 40 left without a reported withdrawal.
    observe(WHEN, 100000)
    observe(WHEN + timedelta(days=3), 100060)
    # 50000 withdrawn the day of that balance, after it was read: the next day's balance
    # is the rest plus Wednesday's yield, so nothing is missing (the withdrawal counts on
    # the earlier side, and only the money left earns).
    withdrawal = {
        "id": str(uuid4()),
        "accountId": CARD,
        "status": "POSTED",
        "currencyCode": "BRL",
        "type": "CREDIT",
        "amount": 50000,
        "date": "2024-11-13",
        "description": "Dinheiro retirado Reserva",
    }
    observe(WHEN + timedelta(days=4), 50060 * 1.0005, [withdrawal])
    rows = [
        json.loads(line)
        for line in silver.execute(
            "SELECT toString(expected_yield) AS earned, toString(amount) AS amount "
            "FROM analytics.savings_box_outflows FORMAT JSONEachRow"
        ).splitlines()
    ]
    assert len(rows) == 1
    assert Decimal(rows[0]["earned"]) == pytest.approx(Decimal("100.025"), abs=Decimal("0.01"))
    assert Decimal(rows[0]["amount"]) == pytest.approx(Decimal("40.025"), abs=Decimal("0.01"))


def test_boleto_is_not_an_own_transfer_even_when_the_bank_reports_the_payer_as_receiver():
    owner = {"documentNumber": {"type": "CPF", "value": "123.456.789-09"}}
    record = {
        "type": "DEBIT",
        "description": "BANKSLIP",
        "category": "Same person transfer",
        "operationType": "BOLETO",
        "paymentData": {"paymentMethod": "BOLETO", "payer": owner, "receiver": owner},
    }
    owners = frozenset({"12345678909"})
    fields = spending_fields(record, "tx", owners=owners)
    assert not fields["own_transfer"]
    assert fields["spending_kind"] == "review"
    pix = record | {"description": "PIX", "operationType": "PIX"}
    pix["paymentData"] = record["paymentData"] | {"paymentMethod": "PIX"}
    fields = spending_fields(pix, "tx", owners=owners)
    assert fields["own_transfer"] and fields["spending_kind"] == ""
