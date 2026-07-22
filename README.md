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

Upload a Polarsteps ZIP, edit the generated album in the browser, and export it
to PDF.

- Automatic photo layouts with drag-and-drop editing
- Map pages with satellite imagery and elevation profiles
- Original-quality photo imports from Google Photos
- Frame selection for video posters
- English, Hebrew, and RTL support

<p align="center">
  <img src="frontend/public/landing/hike-map-dark.jpg" width="240" alt="Map page with satellite imagery and elevation profile">&nbsp;
  <img src="frontend/public/landing/overview-dark.jpg" width="240" alt="Trip overview page">&nbsp;
  <img src="frontend/public/landing/auto-album-dark.jpg" width="240" alt="Auto-generated photo grid layout">
</p>

## Self-Hosting

Requires [Docker Compose](https://docs.docker.com/compose/).

```bash
git clone https://github.com/itay-raveh/wanderbound.git
cd wanderbound
cp .env.example .env
# Set the required values in .env
docker compose up -d
```

Open `http://localhost:8000`.

## Development

Requires [mise](https://mise.jdx.dev/).

```bash
mise run setup
mise run dev
```

Open `http://localhost:5173`. Run `mise tasks` for other commands.
