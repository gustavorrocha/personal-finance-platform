"""Private Lake operations, provider sync, and offline replay."""

import argparse
import base64
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import httpx
from finance_lake import LocalObjectStore
from finance_lake.bronze import BronzeLake, CapturePage
from finance_pluggy.client import AuditError
from finance_pluggy.coverage import audit_from_environment, configured_client, identifier

from .agent import Busy, JobError, serve, writer_lock
from .backup import export_archive, import_archive
from .collection import collect, entity_key, item_key
from .market import sync_market
from .silver import SilverWarehouse
from .spending_demo import load_account_demo, load_demo, load_investment_demo
from .synthetic import capture_synthetic
from .warehouse import BronzeWarehouse


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Invalid finance command; use --help for supported arguments.\n")


def private_root() -> Path:
    private = os.environ.get("FINANCE_PRIVATE_DIR")
    if not private:
        raise ValueError("Configure private storage before operating the Lake")
    return Path(private)


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


def sync(silver: SilverWarehouse, *, full: bool) -> dict:
    runs = []
    with configured_client(max_pages=100) as (client, items):
        for item_id in items:
            run_id = uuid4()
            item = item_key(item_id)
            observed = datetime.now(UTC)
            manifest = None
            silver.event(run_id, item, "started")
            try:
                checkpoint = None if full else silver.checkpoint(item)
                manifest = collect(client, silver.lake, item_id, run_id, observed, checkpoint)
                records = silver.replay(run_id)
            except (RuntimeError, ValueError, OSError, subprocess.SubprocessError):
                if manifest is None:
                    silver.lake.record_collection_failure(run_id, observed)
                silver.event(
                    run_id, item, "capture_failed" if manifest is None else "replay_failed"
                )
                runs.append({"run_id": str(run_id), "status": "failed"})
            else:
                runs.append(
                    {
                        "run_id": str(run_id),
                        "status": manifest.capture_kind,
                        "records": records,
                    }
                )
    return {"runs": runs}


def update(silver: SilverWarehouse) -> dict:
    """What the dashboard's update button runs: provider sync, then public prices."""
    try:
        runs = sync(silver, full=False)["runs"]
    except AuditError:
        return {"failed": True, "error": "credentials"}
    detail = {
        "connections": len(runs),
        "failed": sum(run["status"] in ("failed", "partial") for run in runs),
        "records": sum(run.get("records", 0) for run in runs),
    }
    try:
        with httpx.Client(timeout=120, trust_env=False) as http:
            sync_market(docker_sql, http)
    except (httpx.HTTPError, ValueError, RuntimeError, subprocess.SubprocessError):
        detail["market"] = "failed"
    return detail


def replayer(silver: SilverWarehouse, warehouse: BronzeWarehouse):
    def replay(run_id: UUID) -> int:
        target = silver if warehouse.read_manifest(run_id).source == "pluggy" else warehouse
        return target.replay(run_id)

    return replay


def agent_jobs(private: Path, silver: SilverWarehouse, warehouse: BronzeWarehouse) -> dict:
    """What the dashboard can ask the host agent to do; archives travel through ClickHouse."""

    def locked_update(_request: str) -> dict:
        with writer_lock(private):
            return update(silver)

    def export(request: str) -> dict:
        with writer_lock(private):
            data = export_archive(docker_sql, silver.lake.store)
        row = {
            "request_id": str(UUID(request)),
            "direction": "export",
            "data": base64.b64encode(data).decode(),
        }
        docker_sql(
            "INSERT INTO core.agent_files (request_id, direction, data) FORMAT JSONEachRow",
            json.dumps(row).encode(),
        )
        return {"bytes": len(data)}

    def restore(request: str) -> dict:
        encoded = docker_sql(
            "SELECT data FROM core.agent_files WHERE direction = 'import' "
            f"AND request_id = toUUID('{UUID(request)}') LIMIT 1 FORMAT TSVRaw"
        )
        data = base64.b64decode(encoded.strip(), validate=True)
        with writer_lock(private):
            return import_archive(docker_sql, silver.lake, data, replayer(silver, warehouse))

    return {"sync": locked_update, "export": export, "import": restore}


def apply_deletions(silver: SilverWarehouse, raw: bytes, received_at: datetime) -> int:
    event = json.loads(raw)
    if not isinstance(event, dict) or event.get("event") != "transactions/deleted":
        raise ValueError("Expected a reviewed transaction deletion event")
    item = item_key(identifier(event.get("itemId")))
    account = entity_key(item, "accounts", identifier(event.get("accountId")))
    event_id = identifier(event.get("eventId"))
    ids = event.get("transactionIds")
    if not isinstance(ids, list) or not 1 <= len(ids) <= 10000:
        raise ValueError("Invalid deletion identities")
    if len({identifier(value) for value in ids}) != len(ids):
        raise ValueError("Duplicate transaction identities")
    if (
        received_at.utcoffset() is None
        or not 1970 <= received_at.year
        or received_at > datetime.now(UTC)
    ):
        raise ValueError("Invalid deletion receipt time")
    if not silver.knows_account(item, account):
        raise ValueError("Deletion event account is outside collected scopes")
    run_id = uuid5(NAMESPACE_URL, f"finance:pluggy:deletion:{event_id}")
    silver.lake.commit(
        run_id=run_id,
        retrieved_at=received_at.astimezone(UTC),
        item_alias=f"item-{item.hex}",
        payloads=[CapturePage("transaction_deletions", raw, account)],
        capture_kind="deletions",
    )
    return silver.replay(run_id)


def main(argv: list[str] | None = None) -> int:
    parser = SafeArgumentParser(prog="finance", description=__doc__)
    parser.add_argument("--root", type=Path, help="Private Lake directory outside Git/cloud sync")
    commands = parser.add_subparsers(dest="command", required=True)
    audit = commands.add_parser("audit-coverage", help="Audit existing Pluggy items")
    audit.add_argument("--redact", action="store_true", help="Redaction is always enabled")
    sync_parser = commands.add_parser("sync", help="Collect existing provider items")
    sync_parser.add_argument("--full", action="store_true", help="Read full available history")
    commands.add_parser("market-sync", help="Download public rates and Tesouro, fund and B3 prices")
    commands.add_parser("sync-agent", help="Run the jobs requested from the dashboard")
    export = commands.add_parser("export", help="Write a backup archive of edits and captures")
    export.add_argument("output", type=Path)
    restore = commands.add_parser("import", help="Add what is missing from a backup archive")
    restore.add_argument("archive", type=Path)
    commands.add_parser("demo-spending", help="Load a synthetic spending connection")
    commands.add_parser("demo-accounts", help="Load synthetic account balances")
    commands.add_parser("demo-investments", help="Load synthetic investment positions")
    deletions = commands.add_parser(
        "apply-deletions", help="Read a reviewed provider event on stdin"
    )
    deletions.add_argument("--received-at", type=datetime.fromisoformat, required=True)
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
    if args.command == "market-sync":
        try:
            with writer_lock(private_root()), httpx.Client(timeout=120, trust_env=False) as http:
                summary = sync_market(docker_sql, http)
        except Busy:
            print("Another update is running; try again when it ends.", file=sys.stderr)
            return 1
        except (httpx.HTTPError, ValueError, RuntimeError, OSError, subprocess.SubprocessError):
            print("Rate download failed; details suppressed.", file=sys.stderr)
            return 1
        print(json.dumps(summary, sort_keys=True))
        return 0
    try:
        root = args.root or private_root() / "lake"
        # The writer lock lives in the private directory, next to the Lake.
        private = root.parent
        lake = BronzeLake(LocalObjectStore(root))
        warehouse = BronzeWarehouse(lake, docker_sql)
        silver = SilverWarehouse(warehouse, docker_sql)
        exit_code = 0
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
                                "source": manifest.source,
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
            target = (
                silver if warehouse.read_manifest(args.run_id).source == "pluggy" else warehouse
            )
            summary = {"status": "complete", "records": target.replay(args.run_id)}
        elif args.command == "sync-agent":
            serve(docker_sql, agent_jobs(private, silver, warehouse))
            return 0
        elif args.command == "export":
            with writer_lock(private):
                data = export_archive(docker_sql, lake.store)
            args.output.write_bytes(data)
            summary = {"status": "complete", "bytes": len(data)}
        elif args.command == "import":
            data = args.archive.read_bytes()
            with writer_lock(private):
                summary = import_archive(docker_sql, lake, data, replayer(silver, warehouse))
        elif args.command == "sync":
            with writer_lock(private):
                summary = sync(silver, full=args.full)
            exit_code = int(any(run["status"] in ("failed", "partial") for run in summary["runs"]))
        elif args.command == "demo-spending":
            summary = {"status": "complete", "records": load_demo(silver)}
        elif args.command == "demo-accounts":
            summary = {"status": "complete", "records": load_account_demo(silver)}
        elif args.command == "demo-investments":
            summary = {"status": "complete", "records": load_investment_demo(silver)}
        elif args.command == "apply-deletions":
            raw = sys.stdin.buffer.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError("Deletion event exceeds the input limit")
            summary = {
                "status": "complete",
                "records": apply_deletions(silver, raw, args.received_at),
            }
        else:
            manifests = [warehouse.read_manifest(run_id) for run_id in lake.list_runs()]
            if not manifests:
                raise FileNotFoundError("Rebuild requires at least one committed capture")
            count = warehouse.rebuild() if any(m.source == "synthetic" for m in manifests) else 0
            count += sum(silver.replay(m.run_id) for m in manifests if m.source == "pluggy")
            summary = {"status": "complete", "records": count}
    except Busy:
        print("Another update is running; try again when it ends.", file=sys.stderr)
        return 1
    except JobError as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception:
        print(
            "Finance operation failed; sensitive details suppressed. "
            "Check storage ownership, integrity and local ClickHouse readiness.",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(summary, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
