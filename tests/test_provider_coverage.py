import json
from uuid import UUID

import httpx
import pytest
from finance_ingestion.cli import main
from finance_pluggy.client import AuditError, Pluggy
from finance_pluggy.coverage import audit_source

FIRST, SECOND, CARD, FUND, THIRD = (str(UUID(int=number)) for number in range(1, 6))
CURSOR = f"?accountId={CARD}&after=opaque%2b%2F%3D"
PRIVATE = "synthetic private text"


def pages(rows, page=1, total_pages=1):
    return httpx.Response(200, json={"page": page, "totalPages": total_pages, "results": rows})


@pytest.mark.parametrize("item_ids", [[FIRST], [FIRST, SECOND, THIRD]])
def test_cli_audit_paginates_and_prints_only_redacted_aggregates(monkeypatch, capsys, item_ids):
    calls = []

    def respond(request):
        assert request.url.host == "api.pluggy.ai" and request.url.scheme == "https"
        path = request.url.path
        calls.append(path)
        if path == "/auth":
            assert request.method == "POST"
            assert json.loads(request.content)["clientSecret"] == PRIVATE
            return httpx.Response(200, json={"apiKey": "synthetic-token"})
        assert request.method == "GET" and request.headers["X-API-KEY"] == "synthetic-token"
        match path:
            case p if p in {f"/items/{item}" for item in item_ids}:
                item = p.rsplit("/", 1)[-1]
                return httpx.Response(
                    200,
                    json={
                        "id": item,
                        "status": "UPDATED",
                        "connector": {
                            "name": PRIVATE,
                            "id": 101 if item == FIRST else 202,
                            "products": ["ACCOUNTS", PRIVATE],
                        },
                    },
                )
            case p if p.endswith("/resources"):
                return pages([{"status": "AVAILABLE", "resourceId": CARD}])
            case "/accounts":
                return (
                    pages([{"id": CARD, "type": "CREDIT", "balance": 98765}])
                    if (request.url.params["itemId"] == FIRST)
                    else pages([])
                )
            case "/v2/transactions":
                if "after" in request.url.params:
                    assert request.url.query == CURSOR[1:].encode()
                    return httpx.Response(
                        200,
                        json={
                            "results": [{"date": "2026-10-18T01:00:00Z"}],
                            "next": None,
                        },
                    )
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            {"date": "2026-11-17", "description": PRIVATE, "amount": 98765}
                        ],
                        "next": CURSOR,
                    },
                )
            case "/bills":
                page = int(request.url.params["page"])
                return pages([{"dueDate": f"2026-0{page}-15", "totalAmount": 98765}], page, 2)
            case "/investments":
                return (
                    pages([{"id": FUND, "name": f"Cofrinho {PRIVATE}", "date": "2026-10-18"}])
                    if (request.url.params["itemId"] == SECOND)
                    else pages([])
                )
            case p if p == f"/investments/{FUND}/transactions":
                return httpx.Response(403, json={"message": PRIVATE})
        pytest.fail("Unexpected request")

    for name, value in {
        "CLIENT_ID": str(UUID(int=5)),
        "CLIENT_SECRET": PRIVATE,
        "ITEM_IDS": json.dumps(item_ids),
    }.items():
        monkeypatch.setenv(f"PLUGGY_{name}", value)
    monkeypatch.delenv("FINANCE_PRIVATE_DIR", raising=False)
    transport = httpx.MockTransport(respond)
    real_client = httpx.Client

    def test_client(**kwargs):
        assert kwargs["trust_env"] is False
        return real_client(transport=transport, **kwargs)

    monkeypatch.setattr("finance_pluggy.coverage.httpx.Client", test_client)
    assert main(["audit-coverage", "--redact"]) == 0
    output = capsys.readouterr()
    sources = json.loads(output.out)["sources"]
    assert [row["source"] for row in sources] == [f"item-{i}" for i in range(1, len(item_ids) + 1)]
    first = sources[0]
    assert output.err == ""
    assert first["connector_products"] == ["ACCOUNTS"]
    assert first["transactions"] == {
        "status": "observed",
        "count": 2,
        "scopes_read": 1,
        "scopes_unavailable": 0,
        "first_month": "2026-10",
        "last_month": "2026-11",
        "dated_count": 2,
    }
    assert first["bills"]["count"] == 2
    assert first["savings_pots"] == {"status": "not_observed", "name_matches": 0}
    if len(sources) > 1:
        assert sources[1]["savings_pots"] == {"status": "candidate", "name_matches": 1}
        assert sources[1]["investment_movements"]["status"] == "unavailable"
        assert sources[1]["connector_id"] == sources[2]["connector_id"]
        assert first["connector_id"] != sources[1]["connector_id"]
    assert calls.count("/auth") == 1
    for secret in (
        PRIVATE,
        FIRST,
        SECOND,
        THIRD,
        CARD,
        FUND,
        "synthetic-token",
        "98765",
        "2026-11-17",
    ):
        assert secret not in output.out


@pytest.mark.parametrize(
    "next_query",
    [
        "https://untrusted.example/?token=private",
        f"?accountId={SECOND}&after=other",
        f"?accountId={CARD}&accountId={SECOND}&after=duplicate",
    ],
)
def test_cursor_cannot_change_origin_or_account(next_query):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"results": [], "next": next_query})

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        client = Pluggy(http, max_pages=2)
        client.api_key = "synthetic-token"
        with pytest.raises(AuditError, match="cursor"):
            list(client.records("/v2/transactions", accountId=CARD))
    assert len(calls) == 1


def test_wrong_item_stops_before_any_financial_resource_read():
    def respond(request):
        assert request.url.path == f"/items/{FIRST}"
        return httpx.Response(200, json={"id": SECOND, "connector": {"name": PRIVATE}})

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        client = Pluggy(http, max_pages=2)
        client.api_key = "synthetic-token"
        with pytest.raises(AuditError, match="Invalid Pluggy item"):
            audit_source(client, "item-1", FIRST)


def test_no_redirect_and_auth_error_body_is_omitted():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            307, headers={"Location": "https://untrusted.example/"}, json={"message": PRIVATE}
        )

    with httpx.Client(transport=httpx.MockTransport(respond), follow_redirects=True) as http:
        with pytest.raises(AuditError, match=r"HTTP 307") as error:
            Pluggy(http, max_pages=2).authenticate(FIRST, PRIVATE)
    assert PRIVATE not in str(error.value)
    assert len(calls) == 1


def test_missing_configuration_fails_without_network_or_lake(monkeypatch, capsys):
    for name in ("CLIENT_ID", "CLIENT_SECRET", "ITEM_IDS"):
        monkeypatch.delenv(f"PLUGGY_{name}", raising=False)
    monkeypatch.delenv("FINANCE_PRIVATE_DIR", raising=False)
    assert main(["audit-coverage"]) == 1
    assert "PLUGGY_CLIENT_ID" in capsys.readouterr().err


@pytest.mark.parametrize(
    "item_ids",
    [json.dumps([FIRST, UUID(FIRST).hex]), "[]", json.dumps([PRIVATE]), "invalid-json"],
)
def test_invalid_item_lists_fail_before_authentication(monkeypatch, capsys, item_ids):
    monkeypatch.setenv("PLUGGY_CLIENT_ID", FIRST)
    monkeypatch.setenv("PLUGGY_CLIENT_SECRET", PRIVATE)
    monkeypatch.setenv("PLUGGY_ITEM_IDS", item_ids)

    def no_network(**kwargs):
        pytest.fail("Invalid configuration must fail before opening the HTTP client")

    monkeypatch.setattr("finance_pluggy.coverage.httpx.Client", no_network)
    assert main(["audit-coverage"]) == 1
    assert PRIVATE not in capsys.readouterr().err
