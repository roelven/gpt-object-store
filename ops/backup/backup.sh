#!/bin/bash

# GPT Object Store Database Backup Script
# Performs nightly PostgreSQL backup with rotation

set -euo pipefail

# Configuration from environment variables
POSTGRES_HOST="${POSTGRES_HOST:-db}"
POSTGRES_USER="${POSTGRES_USER:-gptstore}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-change-me}"
POSTGRES_DB="${POSTGRES_DB:-gptstore}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
BACKUP_DIR="/backups"

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"

# Generate timestamp for backup filename
TIMESTAMP=$(date +"%Y-%m-%d-%H%M")
BACKUP_FILE="$BACKUP_DIR/backup-$TIMESTAMP.dump"

# Log start of backup
echo "$(date): Starting backup of database $POSTGRES_DB"

# Set PostgreSQL password
export PGPASSWORD="$POSTGRES_PASSWORD"

# Perform backup using custom format for selective restore capability
if pg_dump \
    --host="$POSTGRES_HOST" \
    --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB" \
    --format=custom \
    --compress=9 \
    --verbose \
    --file="$BACKUP_FILE"; then
    
    echo "$(date): Backup completed successfully: $BACKUP_FILE"
    
    # Get backup file size for logging
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "$(date): Backup size: $BACKUP_SIZE"
    
else
    echo "$(date): ERROR: Backup failed for database $POSTGRES_DB" >&2
    exit 1
fi

# Cleanup old backups
echo "$(date): Cleaning up backups older than $BACKUP_RETENTION_DAYS days"

# Find and remove backup files older than retention period
DELETED_COUNT=$(find "$BACKUP_DIR" -name "backup-*.dump" -type f -mtime +$BACKUP_RETENTION_DAYS -delete -print | wc -l)

if [ "$DELETED_COUNT" -gt 0 ]; then
    echo "$(date): Deleted $DELETED_COUNT old backup files"
else
    echo "$(date): No old backup files to delete"
fi

# List current backups
CURRENT_BACKUPS=$(find "$BACKUP_DIR" -name "backup-*.dump" -type f | wc -l)
echo "$(date): Current backup count: $CURRENT_BACKUPS"

# Verify backup integrity by checking if it's a valid PostgreSQL dump
if pg_restore --list "$BACKUP_FILE" > /dev/null 2>&1; then
    echo "$(date): Backup integrity verified: $BACKUP_FILE"
else
    echo "$(date): WARNING: Backup integrity check failed for $BACKUP_FILE" >&2
fi

echo "$(date): Backup process completed"

# Unset password for security
unset PGPASSWORD