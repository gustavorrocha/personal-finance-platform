"""Data update, backup and restore jobs. The host agent does the work; see finance sync-agent."""

import base64
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from .spending import DEMO_ITEM, ORIGINS, dashboard_query, same_origin

router = APIRouter()
# The agent beats every 30 seconds; allow for one missed beat and a slow poll.
AGENT_TIMEOUT_SECONDS = 90
# The API container has 256 MiB; the body is held raw and base64 encoded at once.
MAX_IMPORT_BYTES = 32 * 1024 * 1024
KINDS = ("sync", "export", "import")


async def clickhouse(query: str, body: bytes | None = None) -> bytes:
    """Raw ClickHouse call for archives, which do not fit JSONEachRow parameters."""
    password = Path("/run/secrets/dashboard_password").read_text(encoding="utf-8").strip()
    async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
        response = await client.post(
            "http://clickhouse:8123/",
            params={"query": query} if body is not None else None,
            content=body if body is not None else query,
            auth=("dashboard", password),
        )
        response.raise_for_status()
        return response.content


def iso(column: str) -> str:
    return f"concat(replaceOne(toString({column}), ' ', 'T'), 'Z')"


async def latest_request(kind: str) -> dict | None:
    rows = await dashboard_query(
        f"SELECT toString(request_id) AS id, {iso('requested_at')} AS requested_at "
        "FROM core.agent_requests WHERE kind = {kind:String} "
        "ORDER BY requested_at DESC LIMIT 1 FORMAT JSONEachRow",
        kind=kind,
    )
    if not rows:
        return None
    request = rows[0]
    events = await dashboard_query(
        "SELECT argMax(event, recorded_at) AS event, argMax(detail, recorded_at) AS detail, "
        f"{iso('max(recorded_at)')} AS at FROM metadata.agent_events "
        "WHERE request_id = {request:UUID} HAVING count() > 0 FORMAT JSONEachRow",
        request=request["id"],
    )
    if not events:
        return {**request, "state": "queued"}
    event = events[0]
    if event["event"] == "started":
        return {**request, "state": "running", "started_at": event["at"]}
    return {
        **request,
        "state": event["event"],
        "finished_at": event["at"],
        "detail": json.loads(event["detail"] or "{}"),
    }


async def queue(kind: str, request_id: str | None = None) -> None:
    current = await latest_request(kind)
    if current and current["state"] in ("queued", "running"):
        raise HTTPException(409, "This job is already queued or running")
    await dashboard_query(
        "INSERT INTO core.agent_requests (request_id, kind) SELECT {request:UUID}, {kind:String}",
        request=request_id or str(uuid4()),
        kind=kind,
    )


@router.get("/api/sync")
async def sync_status():
    beat = await dashboard_query(
        "SELECT dateDiff('second', max(recorded_at), now64(6)) AS age "
        "FROM metadata.agent_events WHERE event = 'heartbeat' "
        "HAVING count() > 0 FORMAT JSONEachRow"
    )
    connections = await dashboard_query(
        "SELECT toString(p.item_key) AS item, n.institution AS institution, "
        f"{iso('max(p.observed_at)')} AS synced_at "
        "FROM metadata.ingestion_publications AS p FINAL "
        "LEFT JOIN analytics.connection_names AS n ON n.item_key = p.item_key "
        "WHERE p.kind IN ('full', 'incremental') AND p.item_key != {demo:UUID} "
        "GROUP BY item, institution ORDER BY synced_at DESC FORMAT JSONEachRow",
        demo=DEMO_ITEM,
    )
    jobs = {kind: await latest_request(kind) for kind in KINDS}
    return {
        "agent": bool(beat) and int(beat[0]["age"]) <= AGENT_TIMEOUT_SECONDS,
        "request": jobs["sync"],
        "export": jobs["export"],
        "import": jobs["import"],
        "connections": connections,
    }


@router.post("/api/sync", status_code=202, dependencies=[Depends(same_origin)])
async def request_sync():
    await queue("sync")
    return await sync_status()


@router.post("/api/backup/export", status_code=202, dependencies=[Depends(same_origin)])
async def request_export():
    await queue("export")
    return await sync_status()


@router.get("/api/backup/export")
async def download_export():
    current = await latest_request("export")
    if not current or current["state"] != "succeeded":
        raise HTTPException(404, "No backup is ready")
    encoded = await clickhouse(
        "SELECT data FROM core.agent_files WHERE direction = 'export' "
        f"AND request_id = toUUID('{current['id']}') LIMIT 1 FORMAT TSVRaw"
    )
    if not encoded.strip():
        raise HTTPException(404, "The backup expired; export it again")
    day = datetime.now(UTC).date().isoformat()
    return Response(
        base64.b64decode(encoded.strip()),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="finance-backup-{day}.zip"'},
    )


@router.post("/api/backup/import", status_code=202)
async def request_import(request: Request):
    if request.headers.get("origin") not in ORIGINS:
        raise HTTPException(403, "Open the local dashboard to import a backup")
    if request.headers.get("content-type", "").split(";", 1)[0] != "application/zip":
        raise HTTPException(415, "Expected a backup archive")
    data = await request.body()
    if not data or len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(413, "The backup archive is empty or too large")
    current = await latest_request("import")
    if current and current["state"] in ("queued", "running"):
        raise HTTPException(409, "This job is already queued or running")
    request_id = str(uuid4())
    row = {"request_id": request_id, "direction": "import", "data": base64.b64encode(data).decode()}
    await clickhouse(
        "INSERT INTO core.agent_files (request_id, direction, data) FORMAT JSONEachRow",
        json.dumps(row).encode(),
    )
    await queue("import", request_id)
    return await sync_status()
