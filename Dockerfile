# syntax=docker/dockerfile:1

FROM oven/bun:1-debian AS frontend-build

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY package.json bun.lock ./
COPY frontend/package.json frontend/package.json

WORKDIR /app/frontend
RUN bun install --frozen-lockfile

COPY frontend ./
COPY PRIVACY.md TERMS.md /app/
COPY backend/openapi.json /app/backend/openapi.json

RUN bun run build


FROM frontend-build AS frontend-app
RUN find dist -type f -name '*.map' -delete


FROM python:3.14-slim AS app

LABEL org.opencontainers.image.source="https://github.com/itay-raveh/wanderbound"
LABEL org.opencontainers.image.description="Wanderbound"
LABEL org.opencontainers.image.licenses="AGPL-3.0"

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libzimg2 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PLAYWRIGHT_BROWSERS_PATH=/app/browsers \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-workspace --package app

RUN playwright install chromium --with-deps

COPY backend/pyproject.toml backend/alembic.ini /app/backend/
COPY backend/app /app/backend/app
COPY --chmod=755 fixtures/demo /app/fixtures/demo
COPY --from=frontend-app /app/frontend/dist /app/frontend/dist

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --package app

ARG APP_VERSION
ENV APP_VERSION=$APP_VERSION

WORKDIR /app/backend

RUN groupadd -r appuser \
    && useradd -r -g appuser -s /sbin/nologin appuser \
    && mkdir -p /app/backend/data \
    && chown -R appuser:appuser /app/backend/data

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--log-config", "app/core/uvicorn_logging.json"]


FROM getsentry/sentry-cli:3.6.0 AS sourcemaps

LABEL org.opencontainers.image.source="https://github.com/itay-raveh/wanderbound"
LABEL org.opencontainers.image.description="Wanderbound source maps"
LABEL org.opencontainers.image.licenses="AGPL-3.0"

ARG APP_VERSION
ENV APP_VERSION=$APP_VERSION

COPY --from=frontend-build /app/frontend/dist /sourcemaps
COPY --chmod=755 scripts/upload_sourcemaps.sh /usr/local/bin/upload-sourcemaps

ENTRYPOINT ["/usr/local/bin/upload-sourcemaps"]
