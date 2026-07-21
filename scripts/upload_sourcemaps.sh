#!/bin/sh
set -eu

version=${APP_VERSION:?APP_VERSION is required}
release="wanderbound@${version#v}"

if ! sentry-cli releases new "$release"; then
  sentry-cli releases info "$release" >/dev/null
fi
sentry-cli sourcemaps upload \
  --release "$release" \
  /app/sourcemaps \
  "$@"
sentry-cli releases finalize "$release"
