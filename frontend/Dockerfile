# check=skip=SecretsUsedInArgOrEnv (all ARGs are public frontend config, not secrets)
FROM oven/bun:1 AS build-stage

WORKDIR /app

COPY package.json bun.lock /app/

COPY frontend/package.json /app/frontend/

WORKDIR /app/frontend

RUN bun install --frozen-lockfile

COPY ./frontend /app/frontend
COPY ./PRIVACY.md ./TERMS.md /app/
COPY --from=openapi /app/backend/openapi.json ./openapi.json

ARG VITE_MAX_UPLOAD_GB
ARG VITE_MAPBOX_TOKEN
ARG VITE_GOOGLE_CLIENT_ID
ARG VITE_CONTACT_EMAIL
ARG VITE_GITHUB_URL
ARG VITE_AUTHOR_NAME
ARG VITE_AUTHOR_URL
ARG VITE_SENTRY_DSN
ARG VITE_FRONTEND_URL

RUN bun run build


FROM nginx:1

COPY --from=build-stage /app/frontend/dist/ /usr/share/nginx/html

COPY ./frontend/nginx/nginx.conf /etc/nginx/conf.d/default.conf
COPY ./frontend/nginx/proxy-params.conf /etc/nginx/proxy-params.conf
COPY ./frontend/nginx/security-headers.conf /etc/nginx/security-headers.conf

# Plain-text placeholders (not $VAR) to avoid clashing with nginx variables.
ARG VITE_MAX_UPLOAD_GB
RUN sed -i "s|MAX_UPLOAD_SIZE|${VITE_MAX_UPLOAD_GB:-4}|g" /etc/nginx/conf.d/default.conf

RUN chown -R nginx:nginx /var/cache/nginx /var/log/nginx /run

USER nginx

EXPOSE 8080
