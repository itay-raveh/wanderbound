FROM oven/bun:1-debian AS build-stage

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY package.json bun.lock /app/

COPY frontend/package.json /app/frontend/

WORKDIR /app/frontend

RUN bun install --frozen-lockfile

COPY ./frontend /app/frontend
COPY ./PRIVACY.md ./TERMS.md /app/
COPY ./backend/openapi.json /app/backend/openapi.json

ARG APP_VERSION
ENV APP_VERSION=${APP_VERSION}

RUN --network=none bun run build \
    && cp -a dist /app/frontend-runtime \
    && find /app/frontend-runtime -type f -name '*.map' -delete

FROM nginx:1 AS frontend

ARG APP_VERSION
ENV APP_VERSION=${APP_VERSION}

LABEL org.opencontainers.image.source="https://github.com/itay-raveh/wanderbound"
LABEL org.opencontainers.image.description="Wanderbound frontend"
LABEL org.opencontainers.image.licenses="AGPL-3.0"

RUN apt-get update \
    && apt-get install -y --no-install-recommends jq \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build-stage /app/frontend-runtime/ /usr/share/nginx/html
COPY --from=build-stage /app/frontend/dist/index.html /opt/wanderbound/index.html

COPY ./frontend/nginx/nginx.conf /etc/nginx/templates/default.conf.template
COPY ./frontend/nginx/proxy-params.conf /etc/nginx/proxy-params.conf
COPY --chmod=755 ./frontend/nginx/40-wanderbound-config.sh /docker-entrypoint.d/40-wanderbound-config.sh

ENV NGINX_ENVSUBST_FILTER="BACKEND_HOST|BACKEND_PORT|MAX_UPLOAD_SIZE|UPLOAD_S3_BROWSER_ORIGIN"
ENV BACKEND_HOST=backend
ENV BACKEND_PORT=8000
ENV MAX_UPLOAD_SIZE=4
ENV UPLOAD_S3_BROWSER_ORIGIN=http://localhost:3900

RUN chown -R nginx:nginx \
    /var/cache/nginx \
    /var/log/nginx \
    /run \
    /etc/nginx/conf.d

USER nginx

EXPOSE 8080


FROM getsentry/sentry-cli:2.58.5@sha256:cb8c539da5a608b6afc185ccdf4985d6f625432c0135c731364c1c39aaa62dcf AS sourcemaps

LABEL org.opencontainers.image.source="https://github.com/itay-raveh/wanderbound"
LABEL org.opencontainers.image.description="Wanderbound frontend source maps"
LABEL org.opencontainers.image.licenses="AGPL-3.0"

USER root

ARG APP_VERSION
ENV APP_VERSION=${APP_VERSION}
ENV HOME=/tmp

COPY --from=build-stage --chown=101:101 /app/frontend/dist/assets/ /artifacts/assets

RUN find /artifacts -type f ! -name '*.js' ! -name '*.map' -delete \
    && chmod -R a-w /artifacts

USER 101:101
