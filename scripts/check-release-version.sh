#!/usr/bin/env bash
set -euo pipefail

version=${1:?Usage: check-release-version.sh VERSION}
for repository in itay-raveh/wanderbound itay-raveh/charts/wanderbound; do
  token=$(curl --fail --silent --show-error --max-time 30 \
    "https://ghcr.io/token?service=ghcr.io&scope=repository:$repository:pull" | jq -er '.token')
  status=$(curl --silent --show-error --max-time 30 --output /dev/null --write-out '%{http_code}' \
    -H "Authorization: Bearer $token" \
    -H 'Accept: application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json' \
    "https://ghcr.io/v2/$repository/manifests/$version")
  if [[ "$status" != 404 ]]; then
    echo "Refusing to publish $repository:$version: manifest lookup returned $status (expected absent 404)." >&2
    exit 1
  fi
done
