from pathlib import Path
from typing import Annotated, Literal

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware


async def check_database() -> bool:
    password = Path("/run/secrets/api_password").read_text(encoding="utf-8").strip()
    async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
        response = await client.post(
            "http://clickhouse:8123/",
            content="SELECT count() FROM metadata.schema_migrations WHERE version = '0001'",
            auth=("health", password),
        )
        response.raise_for_status()
        return response.text.strip() == "1"


class Health(BaseModel):
    status: Literal["ok", "unavailable"]
    phase: Literal[0] = 0


app = FastAPI(title="Personal Finance — Phase 0", version="0.0.0", docs_url=None, redoc_url=None)
app.add_middleware(
    TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "api", "testserver"]
)


@app.middleware("http")
async def safe_responses(request: Request, call_next):
    try:
        response = await call_next(request)
    except Exception:
        # Dependency exceptions can contain secrets; do not serialize or log them.
        response = JSONResponse({"status": "unavailable", "phase": 0}, status_code=503)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/health", response_model=Health, responses={503: {"model": Health}})
async def health(database_ok: Annotated[bool, Depends(check_database)]):
    if not database_ok:
        return JSONResponse({"status": "unavailable", "phase": 0}, status_code=503)
    return Health(status="ok")
