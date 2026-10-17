#!/usr/bin/env bash
set -euo pipefail

revision=$(git rev-parse HEAD)
gh api --method GET "repos/${GITHUB_REPOSITORY:?}/actions/workflows/ci.yml/runs" \
  -f head_sha="$revision" -f branch=main -f event=push -f per_page=1 |
  jq -e --arg revision "$revision" '
    .workflow_runs[0] |
    .head_sha == $revision and .head_branch == "main" and .event == "push" and
    .status == "completed" and .conclusion == "success"
  ' > /dev/null || {
    echo "Release requires completed successful main CI for $revision. Retry after CI passes." >&2
    exit 1
  }
