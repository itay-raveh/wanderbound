#!/usr/bin/env bash
set -euo pipefail

stale=()

check() {
  local name="$1"; shift
  local -a outputs=() inputs=()
  while [[ $# -gt 0 && "$1" != "--" ]]; do outputs+=("$1"); shift; done
  [[ "${1:-}" == "--" ]] || { echo "check: missing -- separator for '$name'" >&2; exit 2; }
  shift  # skip --
  inputs=("$@")

  local out_time in_time
  out_time=$(git log -1 --format=%ct -- "${outputs[@]}" 2>/dev/null || true)
  in_time=$(git log -1 --format=%ct -- "${inputs[@]}" 2>/dev/null || true)

  # No outputs in git yet or no source history - skip
  [[ -z "$out_time" || -z "$in_time" ]] && return
  # Outputs are newer or same age - fresh
  (( in_time <= out_time )) && return

  stale+=("$name")
}

check landing \
  frontend/public/landing/ -- \
  frontend/src/components/album/ \
  frontend/src/App.vue \
  backend/app/logic/layout/ \
  scripts/generate-landing.ts \
  frontend/fonts.json \
  fixtures/demo/

check og-image \
  frontend/public/og-image.png -- \
  scripts/generate-og-image.ts \
  frontend/public/logo.svg \
  frontend/fonts.json

check fonts \
  frontend/public/fonts/ frontend/src/styles/fonts.css -- \
  frontend/fonts.json scripts/generate_fonts.py

check countries \
  frontend/public/countries/ -- \
  scripts/generate_countries.py

check topo \
  frontend/public/topo-contours.svg -- \
  scripts/generate_topo.py

if (( ${#stale[@]} )); then
  echo "Stale generated assets: ${stale[*]}"
  echo "Run 'mise run generate' and commit the output."
  exit 1
fi
echo "All generated assets are fresh."
