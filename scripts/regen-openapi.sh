#!/usr/bin/env bash
# Regenerate backend/openapi.json from the FastAPI app. Called by pre-commit
# when backend/app/ files change. Exits nonzero if the spec drifted, prompting
# the developer to stage the regenerated file (mirrors the ruff --fix pattern).
set -euo pipefail

uv run --directory backend python ../scripts/generate_openapi.py

if ! git diff --quiet backend/openapi.json; then
  echo "backend/openapi.json was regenerated. Stage the change and commit again."
  exit 1
fi
