#!/bin/sh
set -eu

alembic upgrade head
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --log-config app/core/uvicorn_logging.json \
  "$@"
