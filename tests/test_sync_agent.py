import json

import pytest
from fastapi.testclient import TestClient
from finance_api import spending
from finance_api import sync as sync_api
from finance_api.main import app
from finance_ingestion.agent import ZERO, Busy, JobError, handle, serve, writer_lock
from finance_pluggy.coverage import credentials_file

ITEM = "11111111-1111-4111-8111-111111111111"
HEADERS = {"Origin": "http://127.0.0.1:8080", "Content-Type": "application/json"}


def test_credentials_file_is_read_from_the_private_directory(tmp_path, monkeypatch):
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "pluggy.env").write_text(
        "# Pluggy\nPLUGGY_CLIENT_ID=abc\nPLUGGY_CLIENT_SECRET='s=1'\n"
        f'PLUGGY_ITEM_IDS=["{ITEM}"]\nOTHER=ignored\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("FINANCE_PRIVATE_DIR", str(tmp_path))
    assert credentials_file() == {
        "PLUGGY_CLIENT_ID": "abc",
        "PLUGGY_CLIENT_SECRET": "s=1",
        "PLUGGY_ITEM_IDS": f'["{ITEM}"]',
    }
    monkeypatch.delenv("FINANCE_PRIVATE_DIR")
    assert credentials_file() == {}


def test_writer_lock_admits_one_writer(tmp_path):
    with writer_lock(tmp_path):
        with pytest.raises(Busy), writer_lock(tmp_path):
            pass
    with writer_lock(tmp_path):
        pass


class FakeSql:
    def __init__(self, queued):
        self.queued = queued
        self.events = []

    def __call__(self, query, native=b""):
        if query.startswith("INSERT"):
            self.events.append(json.loads(native))
            return b""
        queued, self.queued = self.queued, []
        return "".join(f"{request}\t{kind}\n" for request, kind in queued).encode()


def test_agent_merges_queued_updates_and_runs_other_jobs_alone():
    sql = FakeSql([("a", "sync"), ("b", "sync"), ("c", "export")])
    calls = []
    jobs = {
        "sync": lambda request: calls.append(("sync", request)) or {"failed": 0},
        "export": lambda request: calls.append(("export", request)) or {},
    }
    serve(sql, jobs, sleep=lambda _: None, rounds=2)
    assert calls == [("sync", "b"), ("export", "c")]
    events = [(row["request_id"], row["event"]) for row in sql.events]
    assert events == [
        (ZERO, "heartbeat"),
        ("a", "started"),
        ("b", "started"),
        ("a", "succeeded"),
        ("b", "succeeded"),
        ("c", "started"),
        ("c", "succeeded"),
    ]


def fail(error):
    def job(_request):
        raise error

    return job


@pytest.mark.parametrize(
    ("job", "expected"),
    [
        (lambda _: {"failed": 1}, {"failed": 1}),
        (fail(Busy()), {"error": "busy"}),
        (fail(RuntimeError("secret detail")), {"error": "error"}),
        (fail(ValueError("secret detail")), {"error": "error"}),
        (fail(JobError("Not a backup")), {"error": "invalid", "message": "Not a backup"}),
    ],
)
def test_agent_records_failures_without_details(job, expected):
    sql = FakeSql([])
    handle(sql, job, ["a"])
    assert sql.events[-1]["event"] == "failed"
    assert json.loads(sql.events[-1]["detail"]) == expected


def fake_api(monkeypatch, request_rows, events, beat=None):
    inserted = []

    async def query(text, **parameters):
        if text.startswith("INSERT"):
            inserted.append(parameters.get("kind"))
            return []
        if "core.agent_requests" in text:
            return request_rows if parameters.get("kind") == "sync" else []
        if "event = 'heartbeat'" in text:
            return [{"age": beat}] if beat is not None else []
        if "agent_events" in text:
            return events
        return [{"item": ITEM, "institution": "Bank", "synced_at": "2026-01-02T03:04:05Z"}]

    async def raw(text, body=None):
        inserted.append("file")
        return b""

    monkeypatch.setattr(sync_api, "dashboard_query", query)
    monkeypatch.setattr(sync_api, "clickhouse", raw)
    monkeypatch.setattr(spending, "dashboard_query", query)
    return inserted


def test_status_reports_agent_and_latest_request(monkeypatch):
    request = [{"id": ITEM, "requested_at": "2026-01-02T03:00:00Z"}]
    finished = [{"event": "failed", "detail": '{"error": "credentials"}', "at": "x"}]
    fake_api(monkeypatch, request, finished, beat=10)
    with TestClient(app) as client:
        body = client.get("/api/sync").json()
    assert body["agent"] is True
    assert body["request"]["state"] == "failed"
    assert body["request"]["detail"] == {"error": "credentials"}
    assert body["export"] is None
    assert body["connections"][0]["institution"] == "Bank"


def test_request_is_refused_while_one_is_pending(monkeypatch):
    request = [{"id": ITEM, "requested_at": "2026-01-02T03:00:00Z"}]
    inserted = fake_api(monkeypatch, request, [], beat=200)
    with TestClient(app) as client:
        assert client.get("/api/sync").json()["agent"] is False
        assert client.post("/api/sync", headers=HEADERS, content="{}").status_code == 409
        assert client.post("/api/sync", content="{}").status_code == 403
    assert inserted == []


def test_jobs_are_queued(monkeypatch):
    inserted = fake_api(monkeypatch, [], [], beat=5)
    with TestClient(app) as client:
        assert client.post("/api/sync", headers=HEADERS, content="{}").status_code == 202
        assert client.post("/api/backup/export", headers=HEADERS, content="{}").status_code == 202
        assert client.get("/api/backup/export").status_code == 404
    assert inserted == ["sync", "export"]


def test_import_requires_the_dashboard_and_an_archive(monkeypatch):
    inserted = fake_api(monkeypatch, [], [], beat=5)
    archive = {"Origin": "http://127.0.0.1:8080", "Content-Type": "application/zip"}
    with TestClient(app) as client:
        assert client.post("/api/backup/import", content=b"PK").status_code == 403
        assert client.post("/api/backup/import", headers=HEADERS, content=b"PK").status_code == 415
        assert client.post("/api/backup/import", headers=archive, content=b"").status_code == 413
        assert client.post("/api/backup/import", headers=archive, content=b"PK").status_code == 202
    assert inserted == ["file", "import"]
