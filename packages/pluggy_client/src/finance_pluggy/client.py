"""Bounded Pluggy API reads with sanitized errors."""

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from time import sleep
from urllib.parse import parse_qs

import httpx

ORIGIN = "https://api.pluggy.ai"
UUID_PATH = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
READ_PATH = re.compile(
    rf"(?:/items/{UUID_PATH}(?:/resources)?|/accounts|/bills|/v2/transactions|"
    rf"/investments(?:/{UUID_PATH}/transactions)?)"
)


class AuditError(RuntimeError):
    """Safe to show to the operator."""


class Unavailable(AuditError):
    """A read returned a permission, resource, or validation error."""


@dataclass(frozen=True)
class ResponsePage:
    raw: bytes
    data: dict


class Pluggy:
    def __init__(self, http: httpx.Client, max_pages: int):
        self.http = http
        self.max_pages = max_pages
        self.api_key = ""
        self.remaining = 1000

    def authenticate(self, client_id: str, client_secret: str) -> None:
        response = self._request(
            "/auth",
            credentials={
                "clientId": client_id,
                "clientSecret": client_secret,
            },
        ).data
        key = response.get("apiKey")
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.~-]{1,8192}", key):
            raise AuditError("Invalid Pluggy authentication response.")
        self.api_key = key

    def _request(self, path: str, *, params=None, query=None, credentials=None) -> ResponsePage:
        if credentials is not None:
            if path != "/auth":
                raise AuditError("Unsupported Pluggy authentication path.")
        elif not self.api_key or not READ_PATH.fullmatch(path):
            raise AuditError("Unsupported or unauthenticated Pluggy read.")
        url = httpx.URL(ORIGIN + path)
        if query is not None:
            url = url.copy_with(query=query)
        method = "POST" if credentials is not None else "GET"
        headers = {"X-API-KEY": self.api_key} if credentials is None else {}
        for attempt in range(3):
            if self.remaining <= 0:
                raise AuditError("Pluggy request budget reached.")
            self.remaining -= 1
            try:
                with self.http.stream(
                    method,
                    url,
                    params=params,
                    json=credentials,
                    headers=headers,
                    follow_redirects=False,
                ) as response:
                    status = response.status_code
                    if 200 <= status < 300:
                        raw = bytearray()
                        for chunk in response.iter_bytes(chunk_size=65536):
                            raw.extend(chunk)
                            if len(raw) > 8 * 1024 * 1024:
                                raise AuditError("Pluggy response exceeded the size limit.")
                        result = json.loads(raw)
                        if not isinstance(result, dict):
                            raise AuditError("Invalid Pluggy response shape.")
                        return ResponsePage(bytes(raw), result)
            except (httpx.HTTPError, ValueError, RecursionError):
                raise AuditError("Pluggy connection failed or returned invalid JSON.") from None
            if credentials is None and status in (400, 403, 404, 422):
                raise Unavailable("Pluggy resource could not be read.")
            if attempt < 2 and (status == 429 or 500 <= status < 600):
                sleep(2**attempt)
                continue
            raise AuditError(f"Pluggy request failed (HTTP {status}).")
        raise AuditError("Pluggy retry budget reached.")

    def item(self, item_id: str) -> dict:
        return self.item_page(item_id).data

    def item_page(self, item_id: str) -> ResponsePage:
        return self._request(f"/items/{item_id}")

    def records(self, path: str, **filters: str) -> Iterator[dict]:
        for response in self.pages(path, **filters):
            yield from response.data["results"]

    def pages(self, path: str, **filters: str) -> Iterator[ResponsePage]:
        cursor = path == "/v2/transactions"
        query = None
        seen = set()
        for page in range(1, self.max_pages + 1):
            params = None if query is not None else filters
            if not cursor:
                params = {**filters, "page": page, "pageSize": 500}
            response = self._request(path, params=params, query=query)
            data = response.data
            rows = data.get("results")
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise AuditError("Invalid Pluggy results.")
            yield response
            if cursor:
                if "next" not in data:
                    raise AuditError("Missing Pluggy cursor.")
                next_query = data["next"]
                if next_query is None:
                    return
                if (
                    not isinstance(next_query, str)
                    or not re.fullmatch(r"\?[!-~]{1,16384}", next_query)
                    or "#" in next_query
                    or next_query in seen
                ):
                    raise AuditError("Invalid or repeated Pluggy cursor.")
                if parse_qs(next_query[1:], keep_blank_values=True).get("accountId") != [
                    filters["accountId"]
                ]:
                    raise AuditError("Pluggy cursor changed account scope.")
                seen.add(next_query)
                query = next_query[1:].encode("ascii")
            else:
                total = data.get("totalPages")
                actual = data.get("page")
                if (
                    type(total) is not int
                    or total < 0
                    or type(actual) is not int
                    or actual != page
                    or (total == 0 and rows)
                ):
                    raise AuditError("Invalid Pluggy page metadata.")
                if page >= total:
                    return
        raise AuditError("Pluggy page limit reached.")
