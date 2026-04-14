#!/usr/bin/env bash
set -euo pipefail

# Compares the commit time of the most recent commit touching input paths
# against the filesystem mtime of output files. If any input was committed
# after the oldest output was last written, the asset group is stale.
#
# This works locally (where mtime reflects actual regeneration) but NOT
# in CI (where checkout sets all mtimes to now). Used as a pre-push hook.

stale=()

oldest_mtime() {
  local oldest=""
  for path in "$@"; do
    if [[ -d "$path" ]]; then
      while IFS= read -r f; do
        local t
        t=$(stat -c %Y "$f")
        [[ -z "$oldest" || "$t" -lt "$oldest" ]] && oldest="$t"
      done < <(find "$path" -type f)
    elif [[ -f "$path" ]]; then
      local t
      t=$(stat -c %Y "$path")
      [[ -z "$oldest" || "$t" -lt "$oldest" ]] && oldest="$t"
    fi
  done
  echo "${oldest:-}"
}

check() {
  local name="$1"; shift
  local -a outputs=() inputs=()
  while [[ $# -gt 0 && "$1" != "--" ]]; do outputs+=("$1"); shift; done
  [[ "${1:-}" == "--" ]] || { echo "check: missing -- separator for '$name'" >&2; exit 2; }
  shift
  inputs=("$@")

  local out_mtime in_commit in_time
  out_mtime=$(oldest_mtime "${outputs[@]}")
  in_commit=$(git log -1 --format=%H -- "${inputs[@]}" 2>/dev/null || true)
  in_time=$(git log -1 --format=%ct "$in_commit" 2>/dev/null || true)

  [[ -z "$out_mtime" || -z "$in_time" ]] && return
  (( in_time <= out_mtime )) && return

  # If the commit that last changed inputs also changed outputs,
  # they were regenerated together (commit timestamp > file mtime is normal).
  if git log -1 --format=%H -- "${outputs[@]}" 2>/dev/null | grep -q "^$in_commit$"; then
    return
  fi

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
  echo "Run the relevant 'mise run generate:*' task, then push again."
  exit 1
fi
echo "All generated assets are fresh."
