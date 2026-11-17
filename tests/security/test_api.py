import io
import logging

import pytest
from fastapi.testclient import TestClient
from finance_api.main import app, check_database
from finance_api.safe_logging import SafeFormatter


@pytest.fixture
def client():
    async def healthy():
        return True

    app.dependency_overrides[check_database] = healthy
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_health_and_headers(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "phase": 0}
    assert response.headers["x-content-type-options"] == "nosniff"
    assert (
        response.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    )


def test_database_failure_is_generic(client, caplog):
    secret = "synthetic-secret-never-log-this"

    async def failed():
        raise RuntimeError(secret)

    app.dependency_overrides[check_database] = failed
    response = client.get("/health", headers={"Authorization": f"Bearer {secret}"})
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "phase": 0}
    assert secret not in response.text + caplog.text


def test_closed_host_cors_and_no_mutations(client):
    assert client.get("/health", headers={"host": "attacker.example"}).status_code == 400
    response = client.options(
        "/health",
        headers={"Origin": "https://attacker.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in response.headers
    assert client.post("/health").status_code == 405
    assert client.post("/api/admin/sync").status_code == 404


def test_formatter_discards_values_args_and_traceback():
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(SafeFormatter())
    logger = logging.Logger("synthetic")
    logger.addHandler(handler)
    try:
        raise ValueError("synthetic-secret")
    except ValueError:
        logger.exception("Authorization: %s", "synthetic-secret")
    assert "synthetic-secret" not in output.getvalue()
    assert "ERROR" in output.getvalue()
