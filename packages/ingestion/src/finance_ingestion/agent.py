"""Host loop that runs the jobs requested from the dashboard: update, backup, restore.

The API container has no provider credentials and no internet access, so it only queues
a request in ClickHouse; this loop, started next to the stack, runs the update and
records heartbeats and outcomes the dashboard can show. Outcomes hold counts only.
"""

import json
import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

ZERO = "00000000-0000-0000-0000-000000000000"
HEARTBEAT_SECONDS = 30
POLL_SECONDS = 5

Sql = Callable[..., bytes]


class Busy(RuntimeError):
    """Another update holds the writer lock."""


class JobError(ValueError):
    """A job failed for a reason whose message is safe to show (it carries no data)."""


@contextmanager
def writer_lock(private: Path) -> Iterator[None]:
    """One writer at a time across the agent and manual syncs; the OS frees it on exit."""
    stream = open(private / "sync.lock", "a+b")  # noqa: SIM115 - held for the block
    try:
        try:
            if os.name == "nt":
                import msvcrt

                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise Busy from None
        yield
    finally:
        stream.close()


def record(sql: Sql, request_id: str, event: str, detail: dict | None = None) -> None:
    row = {"request_id": request_id, "event": event, "detail": json.dumps(detail or {})}
    sql(
        "INSERT INTO metadata.agent_events (request_id, event, detail) FORMAT JSONEachRow",
        json.dumps(row).encode(),
    )


def pending(sql: Sql) -> list[tuple[str, str]]:
    output = sql(
        "SELECT toString(request_id), kind FROM core.agent_requests WHERE request_id NOT IN "
        "(SELECT request_id FROM metadata.agent_events WHERE event = 'started') "
        "ORDER BY requested_at FORMAT TSV"
    )
    return [tuple(line.split("	")) for line in output.decode().splitlines()]


def handle(sql: Sql, job: Callable[[str], dict], requests: list[str]) -> None:
    """Run one job for the given requests; queued updates all ask for the same thing."""
    for request_id in requests:
        record(sql, request_id, "started")
    try:
        detail = job(requests[-1])
        event = "failed" if detail.get("failed") else "succeeded"
    except Busy:
        event, detail = "failed", {"error": "busy"}
    except JobError as error:
        event, detail = "failed", {"error": "invalid", "message": str(error)[:200]}
    except Exception:  # noqa: BLE001 - the loop must survive; no details leak
        event, detail = "failed", {"error": "error"}
    for request_id in requests:
        record(sql, request_id, event, detail)


def serve(
    sql: Sql,
    jobs: dict[str, Callable[[str], dict]],
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    rounds: int | None = None,
) -> None:
    beat = None
    while rounds is None or rounds > 0:
        try:
            if beat is None or clock() - beat >= HEARTBEAT_SECONDS:
                record(sql, ZERO, "heartbeat")
                beat = clock()
            queued = pending(sql)
            if updates := [request for request, kind in queued if kind == "sync"]:
                handle(sql, jobs["sync"], updates)
            for request, kind in queued:
                if kind != "sync":
                    handle(sql, jobs.get(kind, unknown), [request])
        except Exception:  # noqa: BLE001, S110 - ClickHouse may be restarting; retry later
            pass
        if rounds is not None:
            rounds -= 1
        sleep(POLL_SECONDS)


def unknown(_request: str) -> dict:
    raise JobError("Unknown job")
