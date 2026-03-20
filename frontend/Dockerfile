FROM oven/bun:1 AS build-stage

WORKDIR /app

COPY package.json bun.lock /app/

COPY frontend/package.json /app/frontend/

WORKDIR /app/frontend

RUN bun install --frozen-lockfile

COPY ./frontend /app/frontend
ARG VITE_MAX_UPLOAD_GB
ARG VITE_BACKEND_URL
ARG VITE_MAPBOX_TOKEN
ARG VITE_GOOGLE_CLIENT_ID

RUN bun run build


FROM nginx:1

COPY --from=build-stage /app/frontend/dist/ /usr/share/nginx/html

COPY ./frontend/nginx.conf /etc/nginx/conf.d/default.conf
