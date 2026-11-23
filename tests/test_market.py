from datetime import date

import httpx
import pytest
from finance_ingestion.market import parse, sync_rates


def test_rates_are_parsed_and_stored_per_series():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, json=[{"data": "19/11/2026", "valor": "0.050788"}])

    inserts = []
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        counts = sync_rates(lambda query, rows: inserts.append(rows), http, date(2026, 11, 23))
    assert counts == {"CDI": 1, "SELIC": 1, "IPCA": 1}
    assert seen[0].params["dataInicial"] == "25/11/2016"
    assert b'"day": "2026-11-19", "value": "0.050788"' in inserts[0]


@pytest.mark.parametrize(
    "payload",
    [
        {"erro": "x"},
        [{"data": "2026-11-19", "valor": "1"}],
        [{"data": "19/11/2026", "valor": "NaN"}],
    ],
)
def test_unexpected_rate_payloads_are_rejected(payload):
    with pytest.raises(ValueError):
        parse("CDI", payload)
