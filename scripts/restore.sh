#!/usr/bin/env bash
# Restore database and/or data volume from backups.
# The backup services (db-backup, data-backup) must be running.
#
# Usage:
#   restore.sh list               Show available backups
#   restore.sh db <file>          Restore database
#   restore.sh data <file>        Restore data volume
set -euo pipefail

cd "$(dirname "$0")/.."

validate_path() {
    [[ "$1" =~ ^[a-zA-Z0-9._:/-]+$ ]] && [[ "$1" != *..* ]] && return
    echo "Invalid backup path: $1" >&2; exit 1
}

resolve_volume() {
    local vol
    vol=$(docker volume ls -q --filter "name=$1")
    [ -n "$vol" ] && [ "$(echo "$vol" | wc -l)" -eq 1 ] || {
        echo "Could not uniquely identify volume matching '$1'" >&2; exit 1
    }
    echo "$vol"
}

case "${1:-}" in
    list)
        echo "-- DB backups --"
        docker compose exec db-backup find /backups -name "*.sql.gz" -type f | sort
        echo ""
        echo "-- Data backups --"
        docker compose exec data-backup find /archive -name "*.tar.gz" -type f | sort
        ;;

    db)
        file="${2:?Usage: $0 db <backup-file>}"
        validate_path "$file"
        docker compose stop backend
        echo "Restoring DB from $file..."
        docker compose exec -T db-backup sh -c "
            PGPASSWORD=\$POSTGRES_PASSWORD \
            psql -h \$POSTGRES_HOST -U \$POSTGRES_USER -d \$POSTGRES_DB \
                -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;' &&
            gunzip -c '/backups/$file' |
            PGPASSWORD=\$POSTGRES_PASSWORD \
            psql -h \$POSTGRES_HOST -U \$POSTGRES_USER -d \$POSTGRES_DB
        "
        docker compose start backend
        echo "DB restored."
        ;;

    data)
        file="${2:?Usage: $0 data <backup-file>}"
        validate_path "$file"
        docker compose stop backend
        echo "Restoring data from $file..."
        backup_vol=$(resolve_volume backup-data)
        data_vol=$(resolve_volume app-data)
        docker run --rm \
            -v "$backup_vol:/archive:ro" \
            -v "$data_vol:/data" \
            alpine sh -c "rm -rf /data/* && tar -xzf '/archive/$file' -C /data"
        docker compose start backend
        echo "Data restored."
        ;;

    *)
        echo "Usage:"
        echo "  $0 list               Show available backups"
        echo "  $0 db <file>          Restore database"
        echo "  $0 data <file>        Restore data volume"
        ;;
esac
