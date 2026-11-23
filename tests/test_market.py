import io
import json
import zipfile
from datetime import date
from decimal import Decimal

import httpx
import pytest
from finance_ingestion.market import (
    parse,
    parse_b3,
    parse_funds,
    parse_treasury,
    sync_equities,
    sync_rates,
)


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


def test_treasury_prices_are_the_morning_redemption_price():
    text = (
        "Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;Taxa Venda Manha;"
        "PU Compra Manha;PU Venda Manha;PU Base Manha\n"
        "Tesouro IPCA+;15/08/2032;18/11/2026;7,74;7,86;3121,65;3100,58;3100,58\n"
        "Tesouro Selic;01/03/2027;18/11/2026;0,03;0,04;0,00;0,00;0,00\n"
        "Tesouro IPCA+;15/08/2032;18/11/2015;7,74;7,86;1,00;1,00;1,00\n"
    )
    assert parse_treasury(text, date(2016, 11, 23)) == [
        {
            "source": "TESOURO",
            "asset": "Tesouro IPCA+|2032-08-15",
            "day": "2026-11-18",
            "price": "3100.58",
        }
    ]
    with pytest.raises(ValueError):
        parse_treasury("Data;Valor\n", date(2016, 11, 23))


def test_fund_quotas_are_kept_for_held_funds_only():
    report = (
        "TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;ID_SUBCLASSE;DT_COMPTC;VL_TOTAL;VL_QUOTA;"
        "VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n"
        "CLASSES - FIF;12.345.678/0001-90;;2026-10-01;1.0;44.9907626;1.0;0;0;1\n"
        "CLASSES - FIF;12.345.678/0001-90;SUB1;2026-10-01;1.0;12.5;1.0;0;0;1\n"
        "CLASSES - FIF;11.111.111/0001-11;;2026-10-01;1.0;3.0;1.0;0;0;1\n"
    )
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("inf_diario_fi_202610.csv", report.encode("latin-1"))
    assert parse_funds(archive.getvalue(), {"12345678000190"}) == [
        {"source": "CVM", "asset": "12345678000190", "day": "2026-10-01", "price": "44.9907626"}
    ]


def test_b3_closing_prices_follow_the_quote_factor():
    def record(ticker, market, close, factor):
        line = f"01{'20261118'}02{ticker:<12}{market}".ljust(108)
        return (line + f"{close:013d}").ljust(210) + f"{factor:07d}"

    lines = [
        "00COTAHIST.2026BOVESPA 20261118",
        record("ETFX11", "010", 16440, 1),
        record("UNIT3", "010", 50000, 1000),
        record("ETFX11", "070", 99999, 1),  # options market: ignored
        record("OTHR3", "010", 100, 1),
    ]
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("COTAHIST_D18112026.TXT", "\n".join(lines).encode("latin-1"))
    rows = parse_b3(archive.getvalue(), {"ETFX11", "UNIT3"})
    assert [(row["asset"], Decimal(row["price"])) for row in rows] == [
        ("ETFX11", Decimal("164.4")),
        ("UNIT3", Decimal("0.5")),
    ]
    assert rows[0]["day"] == "2026-11-18"


def test_equity_files_already_downloaded_are_not_fetched_again():
    downloads: list[dict] = []

    def sql(query, payload=b""):
        if "FROM core.provider_versions" in query:
            return b"ETFX11\n"
        if "FROM core.market_downloads" in query:
            return "\n".join(row["file"] for row in downloads).encode()
        if "INTO core.market_downloads" in query:
            downloads.append(json.loads(payload))
        return b""

    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path.rsplit("_", 1)[1])
        return httpx.Response(404)  # nothing published: holidays and future files

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        sync_equities(sql, http, date(2026, 11, 23))
        first = len(requests)
        sync_equities(sql, http, date(2026, 11, 23))
    # Monthly files and recent days are retried; daily files older than five days that
    # never came are holidays and are not asked for again.
    assert "D18112026.ZIP" in requests[first:] and "D02112026.ZIP" not in requests[first:]
    assert len(requests) - first < first
