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
- GPS tracks classified into flights, hikes, drives, and walks - add map pages
  with satellite imagery and elevation profiles
- Videos in albums - scrub frame-by-frame to pick a poster image
- Full RTL and localization support (English and Hebrew)
- PDF export via headless Chromium

<p align="center">
  <img src="frontend/public/landing/hike-map-dark.jpg" width="320" alt="Map page with satellite imagery and elevation profile">&nbsp;
  <img src="frontend/public/landing/overview-dark.jpg" width="320" alt="Trip overview page">&nbsp;
  <img src="frontend/public/landing/localization-dark.jpg" width="320" alt="Hebrew RTL layout">
</p>

## Tech Stack

|                   |                                                                      |
|-------------------|----------------------------------------------------------------------|
| **Backend**       | Python 3.14, FastAPI, SQLAlchemy, Polars, Playwright, Pillow, ffmpeg |
| **Frontend**      | Vue 3, TypeScript, Quasar, Mapbox GL JS                              |
| **Database**      | PostgreSQL 18                                                        |
| **External APIs** | Open-Meteo (elevations + weather), Mapbox (tiles + routing)          |

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

## Scaling Notes

**Single-worker requirement** - The backend uses in-memory state for processing
sessions, PDF render concurrency, and activity debouncing. Running multiple
uvicorn workers or multiple backend containers would break these. To scale
horizontally, move session/semaphore state to Redis first.

**Structured logging** - The backend currently uses Python stdlib logging.
For log aggregation (CloudWatch, Loki, Datadog), switch to JSON-structured
logging (e.g., `python-json-logger`) and add a correlation ID middleware.
