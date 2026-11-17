import hashlib
import subprocess

import pytest

from scripts import phase0


def test_migration_replay_does_not_write(monkeypatch):
    digest = hashlib.sha256((phase0.ROOT / "infra/migrations/0001_foundation.sql").read_bytes())
    replies = iter([b"1", digest.hexdigest().encode()])
    queries = []

    def execute(query):
        queries.append(query)
        return next(replies)

    monkeypatch.setattr(phase0, "sql", execute)
    phase0.migrate()
    assert len(queries) == 2
    assert all("INSERT" not in query for query in queries)


def test_migration_refuses_changed_applied_sql(monkeypatch):
    replies = iter([b"1", b"0" * 64])
    monkeypatch.setattr(phase0, "sql", lambda query: next(replies))
    with pytest.raises(ValueError, match="Applied migration changed"):
        phase0.migrate()


def test_child_failure_does_not_disclose_stderr(monkeypatch):
    monkeypatch.setattr(
        phase0.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(a[0], 1, b"", b"synthetic-secret"),
    )
    with pytest.raises(RuntimeError) as error:
        phase0.command(["synthetic-command"])
    assert "synthetic-secret" not in str(error.value)


def test_sql_keeps_parameter_values_out_of_query(monkeypatch):
    captured = []
    monkeypatch.setattr(
        phase0, "command", lambda args, payload: captured.append((args, payload)) or b""
    )
    query = "SELECT {label:String}"
    label = "'; DROP DATABASE core; --"
    phase0.sql(query, parameters={"label": label})
    args, payload = captured[0]
    assert args[args.index("--query") + 1] == query
    assert args[-1] == "--param_label=" + label
    assert payload == b""
