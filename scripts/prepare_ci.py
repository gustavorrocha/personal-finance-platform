"""Prepare a brand-new, disposable Linux CI directory with synthetic secrets only."""

import hashlib
import os
from pathlib import Path

from scripts.phase0 import validate_private_path


def main() -> None:
    private = validate_private_path(os.environ["FINANCE_PRIVATE_DIR"])
    private.mkdir(mode=0o700, exist_ok=False)
    for directory in ("clickhouse", "clickhouse-logs", "models", "secrets", "keys", "backups"):
        (private / directory).mkdir(mode=0o700)
    password = os.urandom(32).hex()
    (private / "secrets/api_password").write_text(password)
    digest = hashlib.sha256(password.encode()).hexdigest()
    (private / "secrets/health.xml").write_text(
        "<clickhouse><users><health><password_sha256_hex>"
        + digest
        + "</password_sha256_hex><networks><ip>0.0.0.0/0</ip></networks>"
        "<profile>health</profile><quota>default</quota><grants>"
        "<query>GRANT SELECT ON metadata.schema_migrations</query>"
        "</grants></health></users></clickhouse>"
    )
    # The parent is 0700; mounted secret files must be readable by non-root container UIDs.
    for file in (private / "secrets").iterdir():
        file.chmod(0o444)
    (private / "keys/backup.key").write_bytes(os.urandom(32))
    (private / "keys/backup.key").chmod(0o600)
    (private / ".finance-phase0").write_text("synthetic-only-v1")
    Path(".env").write_text(f"FINANCE_PRIVATE_DIR={private.as_posix()}\n")


if __name__ == "__main__":
    main()
