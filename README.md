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

Open `http://localhost:8000`.

For production, set `APP_VERSION` to an exact released `MAJOR.MINOR.PATCH` tag,
`DOMAIN`, and `ENVIRONMENT=production` in `.env`, then run
`docker compose -f compose.yml up -d`.

The Compose stack runs the app, database, and S3-compatible object storage.
Configure database and app data backups in your deployment infrastructure.

The backend stores upload and processing progress in shared storage and Postgres,
so multiple backend workers can serve the same user flow. All backend workers
must use the same `DATA_FOLDER` volume and database.

## Development

[mise](https://mise.jdx.dev/) manages tool versions and all project
commands. Install it, then:

```bash
mise run setup               # Install dependencies and generate assets
mise run dev                 # Start FastAPI, Vite, and dependencies
```

Open `http://localhost:5173`.

Run `mise tasks` to see all available commands. Extra arguments pass
through - e.g., `mise run test:backend -- -k test_auth`.
