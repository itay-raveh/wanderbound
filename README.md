<p align="center">
  <img src="frontend/public/logo.svg" width="128" height="128" alt="Polarsteps Album Generator">
</p>

# Polarsteps Album Generator

Turn your [Polarsteps](https://www.polarsteps.com/) trips into print-ready
photo albums - complete with maps, weather, statistics, and optimized photo
layouts.

Upload your Polarsteps data export, and the app automatically builds a
multipage album from your trip. An interactive editor lets you rearrange
photos, tweak layouts, and customize covers before printing to PDF.

## What You Get

- **Cover pages** - front and back, with your trip photo, title, dates, and
  subtitle
- **Overview page** - Including countries visited, photo count, distance
  traveled adn other stats.
  trip stats (days, distance, photos, steps), and a home-to-furthest-point arc
- **Map pages** - Maps showing Polarsteps tracking data, including automatic
  flight and hiking recognition.
- **Step pages** - Including data like altitude and weather, and an optimized
  photo layout to get you started.
- **Video extraction** - Videos show up in your album, allowing you to select a
  frame.

## Self-Hosting

Don't trust anyone with your photos and personal data :)

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose

### Setup

1. Clone the repo:
   ```bash
   git clone https://github.com/itayraveh/polarsteps-album-generator.git
   cd polarsteps-album-generator
   ```

2. Create your `.env` file:
   ```bash
   cp .env.example .env
   ```

3. Start the services:
   ```bash
   docker compose up -d
   ```

4. Open `http://localhost:5173`, upload your ZIP, and you're in.

### Important Environment Variables

| Variable            | Required | Description        |
|---------------------|----------|--------------------|
| `VITE_MAPBOX_TOKEN` | Yes      | Free; For the maps |


## Development

### Requirements

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Bun](https://bun.sh/) (JavaScript runtime and package manager)
- Python 3.14+

### Getting Started

```bash
# Install dependencies
cd backend && uv sync # Installs Python dependencies
cd .. && bun install  # Installs frontend dependencies

# Start Postgres
docker compose up db -d

# Backend
cd backend
uv run alembic upgrade head
uv run uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend
bun run dev
```

### Commands

```bash
# Backend
uv run pytest                        # Run tests
uv run ruff check app                # Lint
uv run ruff format app               # Format
uv run ty check                      # Type check

# Frontend
bun run dev                          # Dev server
bun run build                        # Production build
bun run lint                         # ESLint
bun run generate-client              # Regenerate API client from OpenAPI schema

# Full stack
docker compose up -d                 # Start everything
docker compose -f compose.yml up -d  # Production mode (no dev overrides)
```

## License

MIT
