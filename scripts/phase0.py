"""Infrastructure checks and encrypted synthetic backup, not a production backup CLI."""

import argparse
import base64
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    str(ROOT / ".env"),
    "-f",
    str(ROOT / "infra/compose.yaml"),
]
TABLE = "metadata.synthetic_events"
MAGIC = b"FINANCE-PHASE0\x01"


def validate_private_path(path: str | Path, repo: Path = ROOT) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute() or str(path).startswith(("\\\\", "//")):
        raise ValueError("Private storage must be an absolute local directory")
    resolved = candidate.resolve()
    repo = repo.resolve()
    if resolved == repo or resolved.is_relative_to(repo) or repo.is_relative_to(resolved):
        raise ValueError("Private storage must be outside the repository")
    cloud_markers = ("onedrive", "dropbox", "google drive", "googledrive", "icloud")
    if any(marker in str(resolved).lower() for marker in cloud_markers):
        raise ValueError("Cloud-synchronized private storage is forbidden")
    for name in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        if os.environ.get(name) and resolved.is_relative_to(Path(os.environ[name]).resolve()):
            raise ValueError("Cloud-synchronized private storage is forbidden")
    return resolved


def encrypt_backup(payload: bytes, key: bytes) -> bytes:
    nonce = os.urandom(12)
    return MAGIC + nonce + AESGCM(key).encrypt(nonce, payload, MAGIC)


def decrypt_backup(artifact: bytes, key: bytes) -> bytes:
    if not artifact.startswith(MAGIC):
        raise ValueError("Invalid backup format")
    offset = len(MAGIC)
    return AESGCM(key).decrypt(artifact[offset : offset + 12], artifact[offset + 12 :], MAGIC)


def command(args: list[str], payload: bytes | None = None, timeout: int = 120) -> bytes:
    result = subprocess.run(args, input=payload, capture_output=True, timeout=timeout, check=False)
    if result.returncode:
        # Child stderr may contain queries, paths or credentials. Never echo it.
        raise RuntimeError("Infrastructure command failed; no child output disclosed")
    return result.stdout


def sql(
    query: str,
    *,
    container: str | None = None,
    native: bytes = b"",
    parameters: dict[str, str] | None = None,
) -> bytes:
    if container:
        prefix = ["docker", "exec", "-i", container]
    else:
        prefix = COMPOSE + ["exec", "-T", "clickhouse"]
    return command(
        prefix
        + ["clickhouse-client", "--host", "127.0.0.1", "--multiquery", "--query", query]
        + [f"--param_{key}={value}" for key, value in (parameters or {}).items()],
        native,
    )


def migrate() -> None:
    for migration in sorted((ROOT / "infra/migrations").glob("[0-9][0-9][0-9][0-9]_*.sql")):
        version = migration.name[:4]
        content = migration.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        exists = sql("EXISTS TABLE metadata.schema_migrations").strip() == b"1"
        if exists:
            previous = sql(
                f"SELECT sha256 FROM metadata.schema_migrations WHERE version='{version}'"
            )
            if previous.strip():
                if previous.strip() != digest.encode():
                    raise ValueError("Applied migration changed; add a new migration instead")
                continue
        sql(content.decode())
        sql(
            "INSERT INTO metadata.schema_migrations (version,sha256) "
            f"VALUES ('{version}','{digest}')"
        )


def load_synthetic() -> None:
    rows = json.loads((ROOT / "tests/fixtures/synthetic/events.json").read_text())
    for row in rows:
        # Values come from this fixed synthetic fixture, never from requests or backup contents.
        sql(
            "INSERT INTO metadata.synthetic_events SELECT {id:UInt64}, {amount:Decimal(18,2)}, "
            "{label:String} WHERE NOT EXISTS "
            "(SELECT 1 FROM metadata.synthetic_events WHERE event_id={id:UInt64})",
            parameters={"id": str(row["event_id"]), "amount": row["amount"], "label": row["label"]},
        )


def backup(private: Path) -> Path:
    native = sql(f"SELECT * FROM {TABLE} ORDER BY event_id FORMAT Native")
    rows = sql(f"SELECT * FROM {TABLE} ORDER BY event_id FORMAT JSONEachRow")
    if not rows.strip():
        raise ValueError("Synthetic dataset is empty")
    document = json.dumps(
        {
            "format": 1,
            "native": base64.b64encode(native).decode(),
            "sha256": hashlib.sha256(native).hexdigest(),
            "rows_sha256": hashlib.sha256(rows).hexdigest(),
            "row_count": len(rows.splitlines()),
        }
    ).encode()
    target = private / "backups" / f"synthetic-{uuid4().hex}.aesgcm"
    key = (private / "keys/backup.key").read_bytes()
    with target.open("xb") as stream:
        stream.write(encrypt_backup(document, key))
        stream.flush()
        os.fsync(stream.fileno())
    return target


def restore_test(private: Path) -> None:
    artifact = backup(private)
    document = json.loads(
        decrypt_backup(artifact.read_bytes(), (private / "keys/backup.key").read_bytes())
    )
    native = base64.b64decode(document["native"], validate=True)
    if document["format"] != 1 or hashlib.sha256(native).hexdigest() != document["sha256"]:
        raise ValueError("Backup integrity failed")
    name = "finance-restore-" + uuid4().hex
    command(COMPOSE + ["run", "--rm", "--no-deps", "-d", "--name", name, "restore"])
    try:
        for _ in range(60):
            try:
                sql("SELECT 1", container=name)
                break
            except RuntimeError:
                time.sleep(1)
        else:
            raise RuntimeError("Isolated restore did not become ready")
        sql((ROOT / "infra/migrations/0001_foundation.sql").read_text(), container=name)
        sql(f"INSERT INTO {TABLE} FORMAT Native", container=name, native=native)
        restored = sql(
            f"SELECT * FROM {TABLE} ORDER BY event_id FORMAT JSONEachRow", container=name
        )
        if (
            hashlib.sha256(restored).hexdigest() != document["rows_sha256"]
            or len(restored.splitlines()) != document["row_count"]
        ):
            raise ValueError("Restored data does not match original events")
    finally:
        command(["docker", "rm", "-f", name])


def verify() -> None:
    summary = json.loads(
        sql(
            f"SELECT count() AS rows, sum(amount)=toDecimal64(10,2) AS total_ok FROM {TABLE} "
            "FORMAT JSONEachRow"
        )
    )
    if summary != {"rows": 2, "total_ok": 1}:
        raise ValueError("Synthetic fixture count or total differs after replay")
    services = ("clickhouse", "api", "web", "ollama")
    for service in services:
        container = command(COMPOSE + ["ps", "-q", service]).decode().strip()
        if not container:
            raise ValueError("Missing service")
        info = json.loads(command(["docker", "inspect", container]))[0]
        bindings = info["HostConfig"].get("PortBindings") or {}
        for ports in bindings.values():
            if any(p["HostIp"] != "127.0.0.1" for p in ports):
                raise ValueError("A port was published outside localhost")
        if service in ("clickhouse", "ollama") and bindings:
            raise ValueError("Sensitive service has published ports")
        if service in ("api", "web"):
            port = "8000/tcp" if service == "api" else "8080/tcp"
            active = info["NetworkSettings"]["Ports"].get(port) or []
            if len(active) != 1 or active[0]["HostIp"] != "127.0.0.1":
                raise ValueError("Required localhost publication is missing")
        for network in info["NetworkSettings"]["Networks"]:
            detail = json.loads(command(["docker", "network", "inspect", network]))[0]
            if not detail["Internal"]:
                options = detail.get("Options") or {}
                if (
                    network != "personal-finance_frontend"
                    or options.get("com.docker.network.bridge.enable_ip_masquerade") != "false"
                    or options.get("com.docker.network.bridge.host_binding_ipv4") != "127.0.0.1"
                ):
                    raise ValueError("Unexpected network or unrestricted outbound NAT")
    addresses = {"127.0.0.1", *socket.gethostbyname_ex(socket.gethostname())[2]}
    for address in addresses:
        for port in (8123, 9000, 11434):
            with socket.socket() as probe:
                probe.settimeout(1)
                if probe.connect_ex((address, port)) == 0:
                    raise ValueError("Sensitive port is reachable on host")
    secret = "synthetic-" + uuid4().hex
    with httpx.Client(trust_env=False, timeout=5) as client:
        for port in (8000, 8080):
            response = client.get(
                f"http://127.0.0.1:{port}/health",
                params={"synthetic_token": secret},
                headers={"Authorization": f"Bearer {secret}"},
            )
            if response.status_code != 200 or response.json().get("status") != "ok":
                raise ValueError("Health check failed")
        if client.get("http://127.0.0.1:8080/").status_code != 200:
            raise ValueError("Web check failed")
    logs = command(COMPOSE + ["logs", "--no-color"]).decode(errors="replace")
    if secret in logs:
        raise ValueError("Synthetic secret was found in logs")
    # Sensitive services must have no egress; the publishing frontend needs host firewall policy.
    image = command(COMPOSE + ["images", "-q", "api"]).decode().strip()
    probe = (
        "import socket; "
        "s=socket.socket(); s.settimeout(3); "
        "code=s.connect_ex(('1.1.1.1',443)); s.close(); "
        "assert code != 0, 'Unexpected external TCP egress'"
    )
    for service in ("clickhouse", "ollama"):
        container = command(COMPOSE + ["ps", "-q", service]).decode().strip()
        command(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                f"container:{container}",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
                "--read-only",
                "--user=10001:10001",
                image,
                "/app/.venv/bin/python",
                "-c",
                probe,
            ]
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "operation",
        choices=["validate-path", "migrate", "load-synthetic", "backup", "restore-test", "verify"],
    )
    parser.add_argument("--private-dir", default=os.environ.get("FINANCE_PRIVATE_DIR"))
    args = parser.parse_args()
    try:
        private = validate_private_path(args.private_dir or "")
        match args.operation:
            case "validate-path":
                pass
            case "migrate":
                migrate()
            case "load-synthetic":
                load_synthetic()
            case "backup":
                backup(private)
            case "restore-test":
                restore_test(private)
            case "verify":
                verify()
    except Exception:
        print(
            "Phase 0 operation failed. Check prerequisites; sensitive output suppressed.",
            file=sys.stderr,
        )
        return 1
    print("Phase 0 operation passed (synthetic data only).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
