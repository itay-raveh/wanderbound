#!/usr/bin/env bash
# Database backup script. Run via cron:
#   0 3 * * * /path/to/scripts/backup.sh >> /path/to/backups/cron.log 2>&1
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

set -a
source "$PROJECT_DIR/.env"
set +a

BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/${POSTGRES_DB}_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

docker compose -f "$PROJECT_DIR/compose.yml" exec -T db \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges \
    | gzip > "$BACKUP_FILE"

if [ ! -s "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file is empty" >&2
    rm -f "$BACKUP_FILE"
    exit 1
fi

echo "Backup: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"

find "$BACKUP_DIR" -name "*.sql.gz" -mtime +"$RETENTION_DAYS" -delete
