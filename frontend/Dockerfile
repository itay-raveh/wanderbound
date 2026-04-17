# check=skip=SecretsUsedInArgOrEnv (all ARGs are public frontend config, not secrets)
FROM oven/bun:1 AS build-stage

WORKDIR /app

COPY package.json bun.lock /app/

COPY frontend/package.json /app/frontend/

WORKDIR /app/frontend

RUN bun install --frozen-lockfile

COPY ./frontend /app/frontend
COPY ./PRIVACY.md ./TERMS.md /app/
COPY ./backend/openapi.json /app/backend/openapi.json

ARG VITE_MAX_UPLOAD_GB
ARG VITE_MAPBOX_TOKEN
ARG VITE_GOOGLE_CLIENT_ID
ARG VITE_CONTACT_EMAIL
ARG VITE_GITHUB_URL
ARG VITE_AUTHOR_NAME
ARG VITE_AUTHOR_URL
ARG VITE_SENTRY_DSN
ARG VITE_FRONTEND_URL
ARG VITE_MICROSOFT_CLIENT_ID
ARG APP_VERSION=0.0.0
ENV APP_VERSION=${APP_VERSION}

RUN bun run build


FROM nginx:1

LABEL org.opencontainers.image.source="https://github.com/itay-raveh/wanderbound"
LABEL org.opencontainers.image.description="Wanderbound frontend"
LABEL org.opencontainers.image.licenses="AGPL-3.0"

COPY --from=build-stage /app/frontend/dist/ /usr/share/nginx/html

COPY ./frontend/nginx/nginx.conf /etc/nginx/templates/default.conf.template
COPY ./frontend/nginx/proxy-params.conf /etc/nginx/proxy-params.conf
COPY ./frontend/nginx/security-headers.conf /etc/nginx/security-headers.conf

ENV NGINX_ENVSUBST_FILTER="BACKEND_HOST|BACKEND_PORT|MAX_UPLOAD_SIZE"
ENV BACKEND_HOST=backend
ENV BACKEND_PORT=8000
ENV MAX_UPLOAD_SIZE=4

RUN chown -R nginx:nginx /var/cache/nginx /var/log/nginx /run /etc/nginx/conf.d

USER nginx

EXPOSE 8080
