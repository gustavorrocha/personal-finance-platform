"""Private Lake operations and read-only provider coverage audit."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

from finance_lake import LocalObjectStore
from finance_lake.bronze import BronzeLake
from finance_pluggy.client import AuditError
from finance_pluggy.coverage import audit_from_environment

from .synthetic import capture_synthetic
from .warehouse import BronzeWarehouse


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Invalid finance command; use --help for supported arguments.\n")


def docker_sql(query: str, native: bytes = b"") -> bytes:
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "personal-finance-clickhouse-1",
            "clickhouse-client",
            "--host",
            "127.0.0.1",
            "--multiquery",
            "--query",
            query,
        ],
        input=native,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("Local ClickHouse operation failed; child output suppressed")
    return result.stdout


def main(argv: list[str] | None = None) -> int:
    parser = SafeArgumentParser(prog="finance", description=__doc__)
    parser.add_argument("--root", type=Path, help="Private Lake directory outside Git/cloud sync")
    commands = parser.add_subparsers(dest="command", required=True)
    audit = commands.add_parser("audit-coverage", help="Audit existing Pluggy items")
    audit.add_argument("--redact", action="store_true", help="Redaction is always enabled")
    lake_parser = commands.add_parser("lake")
    lake_commands = lake_parser.add_subparsers(dest="operation", required=True)
    lake_commands.add_parser("init")
    lake_commands.add_parser("list")
    lake_commands.add_parser("verify")
    ingest = lake_commands.add_parser("ingest-synthetic")
    ingest.add_argument("--fixtures", type=Path, required=True)
    replay = commands.add_parser("replay")
    replay.add_argument("--run-id", type=UUID, required=True)
    rebuild = commands.add_parser("rebuild-warehouse")
    rebuild.add_argument("--from-bronze", action="store_true", required=True)
    args = parser.parse_args(argv)
    if args.command == "audit-coverage":
        try:
            summary = audit_from_environment(max_pages=100)
        except AuditError as error:
            print(str(error), file=sys.stderr)
            return 1
        print(json.dumps(summary, sort_keys=True))
        return 0
    try:
        root = args.root
        if root is None:
            private = os.environ.get("FINANCE_PRIVATE_DIR")
            if not private:
                raise ValueError("Configure private storage before operating the Lake")
            root = Path(private) / "lake"
        lake = BronzeLake(LocalObjectStore(root))
        warehouse = BronzeWarehouse(lake, docker_sql)
        if args.command == "lake":
            match args.operation:
                case "init":
                    summary = {"status": "ready"}
                case "ingest-synthetic":
                    manifest = capture_synthetic(lake, args.fixtures)
                    count = warehouse.index_run(manifest.run_id)
                    summary = {
                        "status": "complete",
                        "run_id": str(manifest.run_id),
                        "objects": count,
                    }
                case "list" | "verify":
                    runs = []
                    for run_id in lake.list_runs():
                        manifest = (
                            lake.verify_run(run_id)
                            if args.operation == "verify"
                            else lake.read_manifest(run_id)
                        )
                        runs.append(
                            {
                                "run_id": str(manifest.run_id),
                                "objects": len(manifest.objects),
                                "integrity": "verified"
                                if args.operation == "verify"
                                else "not-checked",
                                "status": "quarantined"
                                if lake.is_quarantined(manifest.run_id)
                                else "complete",
                            }
                        )
                    summary = {"runs": runs}
        elif args.command == "replay":
            summary = {"status": "complete", "records": warehouse.replay(args.run_id)}
        else:
            summary = {"status": "complete", "records": warehouse.rebuild()}
    except Exception:
        print(
            "Finance operation failed; sensitive details suppressed. "
            "Check storage ownership, integrity and local ClickHouse readiness.",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
