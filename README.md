<p align="center">
  <img src="frontend/public/logo.svg" width="96" height="96" alt="Wanderbound">
</p>

<h1 align="center">Wanderbound</h1>

<p align="center">
  Turn a <a href="https://www.polarsteps.com/">Polarsteps</a> data export into a print-ready photo album.
</p>

<p align="center">
  <a href="https://github.com/itay-raveh/wanderbound/actions/workflows/ci.yml"><img src="https://github.com/itay-raveh/wanderbound/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/itay-raveh/wanderbound/releases"><img src="https://img.shields.io/github/v/release/itay-raveh/wanderbound" alt="Release"></a>
  <a href="https://github.com/itay-raveh/wanderbound/blob/main/LICENSE"><img src="https://img.shields.io/github/license/itay-raveh/wanderbound" alt="License"></a>
</p>

<p align="center">
  <img src="frontend/public/landing/step-page-dark.jpg" width="720" alt="Generated album page with destination info, photo, coordinates, and weather">
</p>

Upload your Polarsteps ZIP and get a laid-out album - covers, overview page,
maps, photo pages - that you can edit in the browser and export to PDF.

- Photo layout algorithm packs images into grids, with drag-and-drop reordering
- Upgrade low-resolution Polarsteps photos with originals from Google Photos
- GPS tracks classified into flights, hikes, drives, and walks - add map pages
  with satellite imagery and elevation profiles
- Videos in albums - scrub frame-by-frame to pick a poster image
- Full RTL and localization support (English and Hebrew)
- PDF export via headless Chromium

<p align="center">
  <img src="frontend/public/landing/hike-map-dark.jpg" width="240" alt="Map page with satellite imagery and elevation profile">&nbsp;
  <img src="frontend/public/landing/overview-dark.jpg" width="240" alt="Trip overview page">&nbsp;
  <img src="frontend/public/landing/auto-album-dark.jpg" width="240" alt="Auto-generated photo grid layout">
</p>

## Tech Stack

|                   |                                                                      |
|-------------------|----------------------------------------------------------------------|
| **Backend**        | Python 3.14, FastAPI, SQLAlchemy, Polars, Playwright, Pillow, ffmpeg |
| **Frontend**       | Vue 3, TypeScript, Quasar, Uppy, Mapbox GL JS                       |
| **Database**       | PostgreSQL 18                                                       |
| **Object storage** | S3-compatible storage, Garage for Compose                           |
| **External APIs**  | Open-Meteo (elevations + weather), Mapbox (tiles + routing), Google Photos Picker (photo upgrade), OpenStreetMap Overpass (named peaks) |

## Self-Hosting

Requires [Docker](https://docs.docker.com/get-docker/) with Compose.

```bash
git clone https://github.com/itay-raveh/wanderbound.git
cd wanderbound

cp .env.example .env
# Fill in the required values

docker compose up -d
```

Open `http://localhost:5173`.

For production, set `DOMAIN` and `ENVIRONMENT=production` in `.env` and run
`docker compose -f compose.yml up -d`.

The Compose stack runs the app, database, and frontend. Configure database and
app data backups in your deployment infrastructure.

The frontend reads its `VITE_*` settings when the container starts. Published
frontend images do not contain one installation's values. Replace the frontend
container after changing those settings.

Published images use immutable `vMAJOR.MINOR.PATCH` release tags. Commits to
`main` do not publish images, and no mutable `latest`, major, or minor aliases
are published.

Frontend source maps are published in a separate image with the same release
tags. To upload a release's maps to your own Sentry project, set
`SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, and `SENTRY_FRONTEND_PROJECT`. Set
`TAG` to the exact deployed frontend release tag. Set `SENTRY_URL` only for a
non-default or self-hosted Sentry server, then run:

```bash
docker compose --profile sentry run --rm sentry-sourcemaps
```

This optional command reads the release from the source-map image. It does not
change the application images or their startup configuration.

The backend stores upload and processing progress in shared storage and Postgres,
so multiple backend workers can serve the same user flow. All backend workers
must use the same `DATA_FOLDER` volume and database.

## Development

[mise](https://mise.jdx.dev/) manages tool versions and all project
commands. Install it, then:

```bash
mise run setup               # Install deps, generate assets, run migrations
docker compose up db -d      # Start Postgres
mise run dev:backend         # FastAPI dev server
mise run dev:frontend        # Vite dev server
```

Run `mise tasks` to see all available commands. Extra arguments pass
through - e.g., `mise run test:backend -- -k test_auth`.
