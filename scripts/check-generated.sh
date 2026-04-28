#!/usr/bin/env bash
set -euo pipefail

name="${1:?Usage: scripts/check-generated.sh <name> <generate-task> <output>...}"
task="${2:?Usage: scripts/check-generated.sh <name> <generate-task> <output>...}"
shift 2

if [[ $# -eq 0 ]]; then
  echo "Usage: scripts/check-generated.sh <name> <generate-task> <output>..." >&2
  exit 2
fi

echo "Checking generated asset group: $name"
mise run "$task"

if git diff --quiet HEAD -- "$@"; then
  echo "Generated outputs match for $name."
  exit 0
fi

echo "Generated outputs changed for $name:"
git diff --name-only -- "$@"
echo
echo "Review and commit the generated output changes, then retry."
exit 1
