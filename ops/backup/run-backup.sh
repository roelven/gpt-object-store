#!/bin/bash

# Simple backup scheduler that runs without cron
# Avoids setpgid permission issues in Docker containers

set -e

# Log startup
echo "$(date): Backup scheduler starting..."

# Function to run backup at specific time
run_backup_at_time() {
    local target_hour=2
    local target_minute=30
    
    while true; do
        current_hour=$(date +%H)
        current_minute=$(date +%M)
        
        # Check if it's time to run backup (02:30)
        if [ "$current_hour" -eq "$target_hour" ] && [ "$current_minute" -eq "$target_minute" ]; then
            echo "$(date): Running scheduled backup..."
            su -c "/scripts/backup.sh" backup >> /var/log/cron.log 2>&1
            # Sleep for 60 seconds to avoid running multiple times in the same minute
            sleep 60
        fi
        
        # Sleep for 30 seconds between checks
        sleep 30
    done
}

# For testing/debugging, also support running backup every N minutes
if [ "${BACKUP_INTERVAL_MINUTES}" ]; then
    echo "$(date): Running in test mode - backup every ${BACKUP_INTERVAL_MINUTES} minutes"
    while true; do
        echo "$(date): Running test backup..."
        su -c "/scripts/backup.sh" backup >> /var/log/cron.log 2>&1
        sleep $((BACKUP_INTERVAL_MINUTES * 60))
    done
else
    # Run in production mode - backup at 02:30 daily
    echo "$(date): Running in production mode - backup daily at 02:30 UTC"
    run_backup_at_time
fi