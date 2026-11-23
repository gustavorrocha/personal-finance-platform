"""Public daily rates (Banco Central) and prices (Tesouro Direto, CVM funds, B3 quotes).

Whole series are downloaded, never anything tied to a holding, so the source learns nothing
about the portfolio.
"""

import hashlib
import io
import json
import re
import zipfile
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


# Tesouro Transparente: every Tesouro Direto bond's daily rates and unit prices since 2002.
TESOURO = (
    "https://www.tesourotransparente.gov.br/ckan/dataset/"
    "df56aa42-484a-4a59-8184-7676580c81e3/resource/796d2059-14e9-44e3-80c9-2d9e30b405c1/"
    "download/PrecoTaxaTesouroDireto.csv"
)


def treasury_asset(title: str, due: date) -> str:
    """Asset key of a bond: its title without the year, and its due date."""
    return f"{title}|{due.isoformat()}"


def parse_treasury(text: str, since: date) -> list[dict]:
    """The morning redemption price (PU Venda Manha), the one brokers report balances at."""
    lines = text.splitlines()
    header = lines[0].split(";") if lines else []
    try:
        title, due, base, price = (
            header.index(name)
            for name in ("Tipo Titulo", "Data Vencimento", "Data Base", "PU Venda Manha")
        )
    except ValueError:
        raise ValueError("Unexpected Tesouro Direto file") from None
    rows = []
    for line in lines[1:]:
        fields = line.split(";")
        try:
            day = datetime.strptime(fields[base], "%d/%m/%Y").date()
            if day < since:
                continue
            value = Decimal(fields[price].replace(".", "").replace(",", "."))
            maturity = datetime.strptime(fields[due], "%d/%m/%Y").date()
        except (IndexError, ValueError, InvalidOperation):
            raise ValueError("Unexpected Tesouro Direto entry") from None
        if not value.is_finite() or value <= 0:
            continue  # bonds not sold that morning carry no price
        rows.append(
            {
                "source": "TESOURO",
                "asset": treasury_asset(fields[title].strip(), maturity),
                "day": day.isoformat(),
                "price": str(value),
            }
        )
    return rows


def sync_market(sql, http: httpx.Client, today: date | None = None) -> dict:
    today = today or date.today()
    counts = sync_rates(sql, http, today)
    response = http.get(TESOURO, follow_redirects=True)
    response.raise_for_status()
    rows = parse_treasury(response.text, today - timedelta(days=3650))
    store_prices(sql, rows)
    counts["TESOURO"] = len(rows)
    counts["CVM"] = sync_funds(sql, http, today)
    counts["B3"] = sync_equities(sql, http, today)
    return counts


# CVM daily report: every fund's quota, one zip per month.
CVM = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_{month}.zip"


def fund_asset(cnpj: str) -> str | None:
    digits = "".join(character for character in cnpj if character.isdigit())
    return digits if len(digits) == 14 else None


def parse_funds(payload: bytes, funds: set[str]) -> list[dict]:
    """Quotas of the given funds (14-digit CNPJs); subclasses are skipped as ambiguous."""
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = [name for name in archive.namelist() if name.endswith(".csv")]
        if len(names) != 1:
            raise ValueError("Unexpected CVM archive")
        text = archive.read(names[0]).decode("latin-1")
    lines = text.splitlines()
    header = lines[0].split(";") if lines else []
    try:
        cnpj, subclass, day, quota = (
            header.index(name)
            for name in ("CNPJ_FUNDO_CLASSE", "ID_SUBCLASSE", "DT_COMPTC", "VL_QUOTA")
        )
    except ValueError:
        raise ValueError("Unexpected CVM report") from None
    rows = []
    for line in lines[1:]:
        fields = line.split(";")
        try:
            asset = fund_asset(fields[cnpj])
            if asset not in funds or fields[subclass]:
                continue
            value = Decimal(fields[quota])
            observed = date.fromisoformat(fields[day])
        except (IndexError, ValueError, InvalidOperation):
            raise ValueError("Unexpected CVM entry") from None
        if value.is_finite() and value > 0:
            rows.append(
                {"source": "CVM", "asset": asset, "day": observed.isoformat(), "price": str(value)}
            )
    return rows


def store_prices(sql, rows: list[dict]) -> None:
    for start in range(0, len(rows), 50000):
        sql(
            "INSERT INTO core.market_prices (source, asset, day, price) FORMAT JSONEachRow",
            "\n".join(json.dumps(row) for row in rows[start : start + 50000]).encode(),
        )


class Downloads:
    """Files of a source already downloaded for the current set of held assets."""

    def __init__(self, sql, source: str, assets: set[str]):
        self.sql, self.source = sql, source
        self.assets = hashlib.sha256(",".join(sorted(assets)).encode()).hexdigest()[:16]
        # source is one of this module's constants and assets a hex digest: no user input.
        self.done = set(
            sql(
                f"SELECT file FROM core.market_downloads WHERE source = '{source}' "
                f"AND assets = '{self.assets}' FORMAT TSV"
            )
            .decode()
            .split()
        )

    def record(self, file: str) -> None:
        self.sql(
            "INSERT INTO core.market_downloads (source, file, assets) FORMAT JSONEachRow",
            json.dumps({"source": self.source, "file": file, "assets": self.assets}).encode(),
        )
        self.done.add(file)


def held(sql, condition: str) -> list[str]:
    return (
        sql(
            "SELECT DISTINCT symbol FROM core.provider_versions WHERE resource = 'investments' "
            f"AND symbol IS NOT NULL AND {condition} FORMAT TSV"
        )
        .decode()
        .splitlines()
    )


def months_back(today: date, count: int = 13) -> list[date]:
    index = today.year * 12 + today.month - 1
    return [date((index - back) // 12, (index - back) % 12 + 1, 1) for back in range(count)]


def sync_funds(sql, http: httpx.Client, today: date) -> int:
    """The last 13 months of the held funds' quotas; months already downloaded are skipped,
    except the last two, which the CVM still revises."""
    funds = {fund_asset(symbol) for symbol in held(sql, "type = 'MUTUAL_FUND'")} - {None}
    if not funds:
        return 0
    downloads = Downloads(sql, "CVM", funds)
    count = 0
    for back, first in enumerate(months_back(today)):
        month = f"{first:%Y%m}"
        if back >= 2 and month in downloads.done:
            continue
        response = http.get(CVM.format(month=month))
        if response.status_code == 404:
            continue  # not published yet
        response.raise_for_status()
        rows = parse_funds(response.content, funds)
        store_prices(sql, rows)
        downloads.record(month)
        count += len(rows)
    return count


# B3 historical quotes: every listed asset's daily trading, one fixed-width file per month
# (published after the month ends) or per day.
B3 = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_{stamp}.ZIP"


def parse_b3(payload: bytes, tickers: set[str]) -> list[dict]:
    """Spot-market (TPMERC 010) closing prices of the given tickers, per quote factor."""
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        if len(names) != 1:
            raise ValueError("Unexpected B3 archive")
        lines = archive.read(names[0]).decode("latin-1").splitlines()
    rows = []
    for line in lines:
        if line[:2] != "01" or line[24:27] != "010" or line[12:24].strip() not in tickers:
            continue
        try:
            day = date(int(line[2:6]), int(line[6:8]), int(line[8:10]))
            price = Decimal(int(line[108:121])) / 100 / int(line[210:217])
        except (ValueError, ZeroDivisionError):
            raise ValueError("Unexpected B3 entry") from None
        if price > 0:
            rows.append(
                {
                    "source": "B3",
                    "asset": line[12:24].strip(),
                    "day": day.isoformat(),
                    "price": str(price),
                }
            )
    return rows


def sync_equities(sql, http: httpx.Client, today: date) -> int:
    """The last 13 months of the held tickers' closing prices: monthly files for closed
    months, daily files for the current one (or a closed month not published yet)."""
    tickers = {
        symbol.upper()
        for symbol in held(sql, "type IN ('EQUITY', 'ETF')")
        if re.fullmatch(r"[A-Za-z0-9]{4,12}", symbol)
    }
    if not tickers:
        return 0
    downloads = Downloads(sql, "B3", tickers)

    def fetch(stamp: str, final: bool) -> int | None:
        """Rows stored; None when the file does not exist (yet)."""
        if stamp in downloads.done:
            return 0
        response = http.get(B3.format(stamp=stamp))
        if response.status_code == 404:
            if final:
                downloads.record(stamp)  # a holiday: no file will come
            return None
        response.raise_for_status()
        rows = parse_b3(response.content, tickers)
        store_prices(sql, rows)
        downloads.record(stamp)
        return len(rows)

    count = 0
    for back, first in enumerate(months_back(today)):
        monthly = fetch(f"M{first:%m%Y}", final=False) if back else None
        if monthly is not None:
            count += monthly
            continue
        day = first
        while day < today and day.month == first.month:
            if day.weekday() < 5:
                # B3 publishes a day's file the next business day; older gaps are holidays.
                count += fetch(f"D{day:%d%m%Y}", final=day < today - timedelta(days=5)) or 0
            day += timedelta(days=1)
    return count
