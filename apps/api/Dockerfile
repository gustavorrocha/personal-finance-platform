FROM ghcr.io/astral-sh/uv:0.11.6 AS uv
FROM python:3.12.12-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONDONTWRITEBYTECODE=1
COPY pyproject.toml uv.lock ./
COPY apps/api apps/api
COPY packages/lake packages/lake
COPY packages/ingestion packages/ingestion
RUN uv sync --frozen --no-dev --no-editable && chown -R 10001:10001 /app
USER 10001:10001
CMD ["/app/.venv/bin/python", "-m", "finance_api"]
