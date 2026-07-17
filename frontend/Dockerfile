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
ARG FRONTEND_ENV_HASH
ENV APP_VERSION=${APP_VERSION}

RUN --mount=type=secret,id=app_env,required=true,target=/app/.env \
    test -n "$FRONTEND_ENV_HASH" \
    && bun run build


FROM nginx:1

LABEL org.opencontainers.image.source="https://github.com/itay-raveh/wanderbound"
LABEL org.opencontainers.image.description="Wanderbound frontend"
LABEL org.opencontainers.image.licenses="AGPL-3.0"

COPY --from=build-stage /app/frontend/dist/ /usr/share/nginx/html

COPY ./frontend/nginx/nginx.conf /etc/nginx/templates/default.conf.template
COPY ./frontend/nginx/proxy-params.conf /etc/nginx/proxy-params.conf
COPY ./frontend/nginx/generated-upload-limits.conf /etc/nginx/generated-upload-limits.conf

ENV NGINX_ENVSUBST_FILTER="BACKEND_HOST|BACKEND_PORT|UPLOAD_S3_BROWSER_ORIGIN"
ENV BACKEND_HOST=backend
ENV BACKEND_PORT=8000

RUN chown -R nginx:nginx /var/cache/nginx /var/log/nginx /run /etc/nginx/conf.d

USER nginx

EXPOSE 8080
