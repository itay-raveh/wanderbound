<p align="center">
  <img src="frontend/public/logo.svg" width="96" height="96" alt="Wanderbound">
</p>

<h1 align="center">Wanderbound</h1>

<p align="center">
  Converts a <a href="https://www.polarsteps.com/">Polarsteps</a> data export into a print-ready photo album.
</p>

Upload your Polarsteps ZIP and get a laid-out album - covers, overview page,
maps, photo pages - that you can edit and export to PDF.

- Photo layout algorithm packs images into grids
- Videos in albums - scrub frame-by-frame to pick a poster
- Drag-and-drop editor
- GPS tracks classified into flights, hikes, driving, walking. Add map pages
  with satellite imagery and elevation profiles
- Album supports any locale (UI in English and Hebrew).
- PDF export

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
git clone https://github.com/itayraveh/polarsteps-album-generator.git
cd polarsteps-album-generator

cp .env.example .env
# Fill in the required values

docker compose up -d
```

Open `http://localhost:5173`.

For production, set `DOMAIN` and `ENVIRONMENT=production` in `.env` and run
`docker compose -f compose.yml up -d`.

## Development

[mise](https://mise.jdx.dev/) manages tool versions (Python 3.14, Bun) and
all project commands. Install it, then:

```bash
mise install            # Install Python + Bun
cd backend && uv sync   # Install backend deps
cd frontend && bun install  # Install frontend deps
```

Start Postgres, run migrations, then the dev servers:

```bash
docker compose up db -d      # Start Postgres
mise run migrate             # Run database migrations
mise run dev:backend         # FastAPI dev server
mise run dev:frontend        # Vite dev server
```

Run `mise tasks` to see everything available:

| Command                  | What it does                         |
|--------------------------|--------------------------------------|
| `mise run test`          | Run all tests (backend + frontend)   |
| `mise run test:backend`  | Backend tests (pytest)               |
| `mise run test:frontend` | Frontend unit tests (vitest)         |
| `mise run test:e2e`      | Frontend E2E tests (playwright)      |
| `mise run lint`          | Lint everything                      |
| `mise run format`        | Auto-format everything               |
| `mise run build`         | Production frontend build            |
| `mise run logs`          | Tail Docker Compose logs             |
| `mise run restore list`  | Show available backups               |

Extra arguments pass through — e.g., `mise run test:backend -k test_auth`
runs only tests matching `test_auth`.

## Roadmap

- [ ] Fix photo focus.
- [ ] Fix reupload.
- [ ] Critique overview page.
- [ ] Critique step main pages.
- [ ] Critique step photo pages.
- [ ] Critique landing.
- [ ] Critique upload.
- [ ] Allow hiding covers, overview.
- [ ] Add controls for zoom, page padding.
- [ ] HDR → SDR tone-mapping for video poster extraction
- [ ] Add "Try with demo data" feature.
- [ ] Add onboarding flow.
- [ ] Add double page photos.
- [ ] Create deployment strategy.

## License

MIT
