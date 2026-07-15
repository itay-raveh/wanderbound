#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
work_dir=$(mktemp -d)
env_file="$work_dir/integration.env"
fixture="$work_dir/direct-upload.zip"
project_name="wanderbound-direct-upload-$(basename "$work_dir" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')"

compose=(
  docker compose
  --project-name "$project_name"
  --env-file "$env_file"
  -f "$root/compose.yml"
  -f "$root/frontend/integration/compose.yml"
)

cleanup() {
  status=$?
  if ((status != 0)); then
    "${compose[@]}" logs --no-color || true
  fi
  "${compose[@]}" down --volumes --remove-orphans || true
  rm -rf "$work_dir"
  exit "$status"
}
trap cleanup EXIT

printf '%s\n' \
  "COMPOSE_PROJECT_NAME=$project_name" \
  "TAG=direct-upload-integration" \
  "SECRET_KEY=integration-only-session-secret" \
  "POSTGRES_PASSWORD=integration-postgres" \
  "POSTGRES_USER=postgres" \
  "POSTGRES_DB=app" \
  "ENVIRONMENT=local" \
  "VITE_ENVIRONMENT=local" \
  "DOMAIN=localhost" \
  "VITE_FRONTEND_URL=http://localhost:5173" \
  "VITE_MAX_UPLOAD_GB=1" \
  "MAX_STORAGE_BYTES=1073741824" \
  "UPLOAD_S3_BUCKET=wanderbound-integration-uploads" \
  "UPLOAD_S3_REGION=garage" \
  "UPLOAD_S3_INTERNAL_ENDPOINT_URL=http://object-storage:3900" \
  "UPLOAD_S3_PUBLIC_ENDPOINT_URL=http://localhost:3900" \
  "UPLOAD_S3_BROWSER_ORIGIN=http://localhost:3900" \
  "UPLOAD_S3_ADDRESSING_STYLE=path" \
  "UPLOAD_S3_ACCESS_KEY_ID=GK00000000000000000000000000000000" \
  "UPLOAD_S3_SECRET_ACCESS_KEY=0000000000000000000000000000000000000000000000000000000000000000" \
  "GARAGE_RPC_SECRET=1111111111111111111111111111111111111111111111111111111111111111" \
  >"$env_file"

set -a
source "$env_file"
set +a
uv run --directory "$root/backend" python ../scripts/generate_openapi.py
python "$root/scripts/generate_direct_upload_fixture.py" "$fixture"
"${compose[@]}" down --volumes --remove-orphans
"${compose[@]}" up --detach --build --wait

cd "$root/frontend"
DIRECT_UPLOAD_FIXTURE="$fixture" bun x playwright test \
  --config playwright.upload-integration.config.ts \
  "$@"
