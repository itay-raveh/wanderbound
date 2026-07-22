# syntax=docker/dockerfile:1

FROM getsentry/sentry-cli:3.6.0 AS sentry-cli


FROM oven/bun:1-debian AS frontend-build

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates musl \
    && rm -rf /var/lib/apt/lists/*

COPY package.json bun.lock ./
COPY frontend/package.json frontend/package.json

WORKDIR /app/frontend
RUN bun install --frozen-lockfile

COPY frontend ./
COPY PRIVACY.md TERMS.md /app/
COPY backend/openapi.json /app/backend/openapi.json

RUN bun run build

COPY --from=sentry-cli /bin/sentry-cli /usr/local/bin/sentry-cli
RUN sentry-cli sourcemaps inject dist


FROM frontend-build AS frontend-app
RUN find dist -type f -name '*.map' -delete


FROM python:3.14-slim

LABEL org.opencontainers.image.source="https://github.com/itay-raveh/wanderbound"
LABEL org.opencontainers.image.description="Wanderbound"
LABEL org.opencontainers.image.licenses="AGPL-3.0"

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libzimg2 musl \
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
COPY --from=frontend-build /app/frontend/dist /app/sourcemaps
COPY --from=sentry-cli /bin/sentry-cli /usr/local/bin/sentry-cli
COPY --chmod=755 scripts/start.sh /usr/local/bin/start-wanderbound
COPY --chmod=755 scripts/upload_sourcemaps.sh /usr/local/bin/upload-sourcemaps

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
    && chown -R appuser:appuser /app/backend

USER appuser

EXPOSE 8000

CMD ["start-wanderbound"]
