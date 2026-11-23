"""Public daily rates from the Banco Central SGS API, to value positions between balances.

Whole series are downloaded, never anything tied to a holding, so the source learns nothing
about the portfolio.
"""

import json
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import httpx

# SGS codes: CDI and Selic as daily percentages, IPCA as a monthly percentage.
SERIES = {"CDI": 12, "SELIC": 11, "IPCA": 433}
URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"


def parse(name: str, payload: object) -> list[dict]:
    if not isinstance(payload, list):
        raise ValueError("Unexpected rate series")
    rows = []
    for entry in payload:
        try:
            day = datetime.strptime(entry["data"], "%d/%m/%Y").date()
            value = Decimal(entry["valor"])
        except (KeyError, TypeError, ValueError, InvalidOperation):
            raise ValueError("Unexpected rate entry") from None
        if not value.is_finite() or abs(value) >= 100:
            raise ValueError("Rate out of range")
        rows.append({"series": name, "day": day.isoformat(), "value": str(value)})
    return rows


def sync_rates(sql, http: httpx.Client, today: date | None = None) -> dict:
    """Download the last ten years (the SGS limit per request) of each series."""
    today = today or date.today()
    window = {
        "formato": "json",
        "dataInicial": (today - timedelta(days=3650)).strftime("%d/%m/%Y"),
        "dataFinal": today.strftime("%d/%m/%Y"),
    }
    counts = {}
    for name, code in SERIES.items():
        response = http.get(URL.format(code=code), params=window)
        response.raise_for_status()
        rows = parse(name, response.json())
        if rows:
            sql(
                "INSERT INTO core.market_rates (series, day, value) FORMAT JSONEachRow",
                "\n".join(json.dumps(row) for row in rows).encode(),
            )
        counts[name] = len(rows)
    return counts
