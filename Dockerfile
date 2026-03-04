# -- Build frontend --
FROM node:20-alpine AS frontend-build

WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# -- Build & run backend --
FROM ghcr.io/astral-sh/uv:python3.14-alpine

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y ffmpeg libsm6 libxext6 && rm -rf /var/lib/apt/lists

# Copy backend
COPY backend/ .

# Copy built frontend into the location expected by main.py
# main.py resolves: Path(__file__).parents[3] / "frontend" / "dist"
# __file__ = /app/src/psagen/main.py → parents[3] = /
COPY --from=frontend-build /frontend/dist /frontend/dist

# Install project dependencies
ENV UV_NO_DEV=1
RUN uv sync --locked

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "psagen.main:app", "--host", "0.0.0.0", "--port", "8000"]
