#!/usr/bin/env bash
# pg-restore.sh — Restore a TBD PostgreSQL backup
#
# Usage:
#   ./pg-restore.sh <backup-file>
#   ./pg-restore.sh /var/lib/tbd/backups/postgres/tbd-tbd-20260304-020000.sql.gz
#
# WARNING: This drops and recreates the target database. All existing
#          data will be lost. Make sure the API is stopped first.

set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-tbd-postgres}"
POSTGRES_USER="${POSTGRES_USER:-tbd}"
POSTGRES_DB="${POSTGRES_DB:-tbd}"

timestamp() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "[$(timestamp)] $*"; }

if [ $# -lt 1 ]; then
    echo "Usage: $0 <backup-file>"
    echo "  e.g. $0 /var/lib/tbd/backups/postgres/tbd-tbd-20260304-020000.sql.gz"
    exit 1
fi

DUMP_PATH="$1"

if [ ! -f "$DUMP_PATH" ]; then
    log "ERROR: Backup file not found: $DUMP_PATH"
    exit 1
fi

if [ ! -s "$DUMP_PATH" ]; then
    log "ERROR: Backup file is empty: $DUMP_PATH"
    exit 1
fi

log "Restoring database '${POSTGRES_DB}' from: ${DUMP_PATH}"
log "WARNING: This will drop and recreate the '${POSTGRES_DB}' database."
read -p "Continue? [y/N] " confirm
if [[ ! "$confirm" =~ ^[yY]$ ]]; then
    log "Aborted."
    exit 0
fi

# Drop connections and recreate the database
log "Dropping existing database..."
docker exec "$CONTAINER_NAME" psql -U "$POSTGRES_USER" -d postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${POSTGRES_DB}' AND pid <> pg_backend_pid();" \
    2>/dev/null || true

docker exec "$CONTAINER_NAME" psql -U "$POSTGRES_USER" -d postgres -c \
    "DROP DATABASE IF EXISTS ${POSTGRES_DB};"

docker exec "$CONTAINER_NAME" psql -U "$POSTGRES_USER" -d postgres -c \
    "CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER};"

# Restore from pg_dump custom format
log "Restoring from backup..."
docker exec -i "$CONTAINER_NAME" \
    pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --verbose --no-owner --no-acl \
    < "$DUMP_PATH"

log "Restore complete. Verify with: docker exec $CONTAINER_NAME psql -U $POSTGRES_USER -d $POSTGRES_DB -c '\\dt'"
