#!/bin/sh
set -eu

web_root=${1:-/var/run/wanderbound}
nginx_config=${2:-/etc/nginx/conf.d/default.conf}
built_index=${3:-/opt/wanderbound/index.html}

fail() {
  printf 'Invalid or missing %s\n' "$1" >&2
  exit 1
}

export VITE_MAX_UPLOAD_GB=${VITE_MAX_UPLOAD_GB:-4}
export VITE_SENTRY_TRACES_SAMPLE_RATE=${VITE_SENTRY_TRACES_SAMPLE_RATE:-0.1}
export VITE_FRONTEND_URL=${VITE_FRONTEND_URL:-http://localhost}

case ${VITE_ENVIRONMENT:-} in
  local | production) ;;
  *) fail VITE_ENVIRONMENT ;;
esac

sentry_origin=
if [ -n "${VITE_SENTRY_DSN:-}" ]; then
  sentry_origin=$(jq -enr --arg value "$VITE_SENTRY_DSN" '
    $value
    | capture("^(?<scheme>https?)://[^/?#@]+@(?<authority>(?:\\[[0-9A-Fa-f:.]+\\]|[A-Za-z0-9.-]+)(?::[0-9]+)?)/[^?#[:space:]]+(?:\\?[^#[:space:]]*)?(?:#[^[:space:]]*)?$")
    | "\(.scheme)://\(.authority)"
  ') || fail VITE_SENTRY_DSN
fi

[ -f "$built_index" ] || fail built_index
[ -f "$nginx_config" ] || fail nginx_config
grep -q '__WANDERBOUND_SENTRY_ORIGIN__' "$nginx_config" || fail nginx_config
mkdir -p "$web_root"

config_tmp=$(mktemp "$web_root/.config.js.XXXXXX")
index_tmp=$(mktemp "$web_root/.index.html.XXXXXX")
nginx_tmp=$(mktemp "$nginx_config.XXXXXX")
trap 'rm -f "$config_tmp" "$index_tmp" "$nginx_tmp"' EXIT HUP INT TERM

{
  printf 'globalThis.WANDERBOUND_CONFIG = '
  jq -cjn '$ENV | with_entries(select(.key | startswith("VITE_")))'
  printf ';\n'
} > "$config_tmp"

escaped_frontend_url=$(jq -nr --arg value "$VITE_FRONTEND_URL" '$value | @html')
jq -Rrs --arg value "$escaped_frontend_url" '
  gsub("__WANDERBOUND_FRONTEND_URL__"; $value)
' "$built_index" > "$index_tmp"

sed "s|__WANDERBOUND_SENTRY_ORIGIN__|$sentry_origin|g" \
  "$nginx_config" > "$nginx_tmp"

mv "$config_tmp" "$web_root/config.js"
mv "$index_tmp" "$web_root/index.html"
mv "$nginx_tmp" "$nginx_config"
trap - EXIT HUP INT TERM
