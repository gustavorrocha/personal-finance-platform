from pathlib import Path

import pytest
from finance_ingestion import cli


def test_list_and_verify_do_not_require_a_database_or_external_network(
    tmp_path, monkeypatch, capsys
):
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError("Offline Lake inspection must not open network sockets")

    monkeypatch.setattr(socket, "socket", forbidden)
    root = str(tmp_path / "lake")
    assert cli.main(["--root", root, "lake", "init"]) == 0
    assert cli.main(["--root", root, "lake", "list"]) == 0
    assert cli.main(["--root", root, "lake", "verify"]) == 0
    assert '"runs": []' in capsys.readouterr().out


def test_cli_preserves_capture_after_database_failure_without_disclosing_details(
    tmp_path, monkeypatch, capsys
):
    def failed(*args, **kwargs):
        raise RuntimeError("synthetic-token-never-print")

    monkeypatch.setattr(cli, "docker_sql", failed)
    root = tmp_path / "lake"
    args = [
        "--root",
        str(root),
        "lake",
        "ingest-synthetic",
        "--fixtures",
        str(Path("tests/fixtures/synthetic").resolve()),
    ]
    assert cli.main(args) == 1
    assert len(list((root / "manifests").rglob("manifest.json"))) == 1
    output = capsys.readouterr()
    assert "synthetic-token-never-print" not in output.err + output.out
    monkeypatch.setattr(cli, "docker_sql", lambda *args, **kwargs: b"")
    assert cli.main(args) == 0
    assert len(list(root.rglob("*.gz"))) == 2


def test_cli_rejects_repository_storage_before_creating_files(capsys):
    assert cli.main(["--root", str(Path("private_data").resolve()), "lake", "init"]) == 1
    assert not Path("private_data").exists()
    assert "Finance operation failed" in capsys.readouterr().err


def test_invalid_cli_arguments_do_not_echo_values(capsys):
    secret = "synthetic-token-never-print"
    with pytest.raises(SystemExit) as error:
        cli.main(["replay", "--run-id", secret])
    assert error.value.code == 2
    output = capsys.readouterr()
    assert secret not in output.out + output.err
