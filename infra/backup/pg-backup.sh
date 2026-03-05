#!/usr/bin/env bash
# pg-backup.sh — Automated PostgreSQL backup for TBD Platform
#
# Creates a compressed pg_dump inside the postgres container, copies it
# to the host backup directory, and prunes old backups beyond the
# retention window.
#
# Usage:
#   ./pg-backup.sh                  # Run a backup
#   BACKUP_DIR=/mnt/backups ./pg-backup.sh  # Custom backup dir
#
# Recommended cron entry (daily at 02:00):
#   0 2 * * * /opt/tbd/infra/backup/pg-backup.sh >> /var/log/tbd-backup.log 2>&1

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration (override via environment)
# ---------------------------------------------------------------------------
CONTAINER_NAME="${CONTAINER_NAME:-tbd-postgres}"
POSTGRES_USER="${POSTGRES_USER:-tbd}"
POSTGRES_DB="${POSTGRES_DB:-tbd}"
BACKUP_DIR="${BACKUP_DIR:-/var/lib/tbd/backups/postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
timestamp() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "[$(timestamp)] $*"; }

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
if ! command -v docker &>/dev/null; then
    log "ERROR: docker not found in PATH"
    exit 1
fi

if ! docker inspect "$CONTAINER_NAME" &>/dev/null; then
    log "ERROR: Container '$CONTAINER_NAME' not found or not running"
    exit 1
fi

mkdir -p "$BACKUP_DIR"

# ---------------------------------------------------------------------------
# Dump
# ---------------------------------------------------------------------------
DUMP_FILENAME="tbd-${POSTGRES_DB}-$(date -u +%Y%m%d-%H%M%S).sql.gz"
DUMP_PATH="${BACKUP_DIR}/${DUMP_FILENAME}"

log "Starting backup of database '${POSTGRES_DB}' from container '${CONTAINER_NAME}'..."

docker exec "$CONTAINER_NAME" \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
        --format=custom \
        --compress=6 \
        --verbose \
    > "$DUMP_PATH" 2>/dev/null

DUMP_SIZE=$(du -sh "$DUMP_PATH" | cut -f1)
log "Backup complete: ${DUMP_FILENAME} (${DUMP_SIZE})"

# ---------------------------------------------------------------------------
# Verify the dump is non-empty
# ---------------------------------------------------------------------------
if [ ! -s "$DUMP_PATH" ]; then
    log "ERROR: Backup file is empty — aborting"
    rm -f "$DUMP_PATH"
    exit 1
fi

# ---------------------------------------------------------------------------
# Prune old backups
# ---------------------------------------------------------------------------
PRUNED=$(find "$BACKUP_DIR" -name "tbd-*.sql.gz" -mtime +"$RETENTION_DAYS" -print -delete | wc -l)
if [ "$PRUNED" -gt 0 ]; then
    log "Pruned ${PRUNED} backup(s) older than ${RETENTION_DAYS} days"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
TOTAL_BACKUPS=$(find "$BACKUP_DIR" -name "tbd-*.sql.gz" | wc -l)
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
log "Backup directory: ${BACKUP_DIR} (${TOTAL_BACKUPS} backups, ${TOTAL_SIZE} total)"
log "Done."
