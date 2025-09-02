#!/bin/sh

# Entrypoint script for backup container
# Runs crond as root but executes backups as backup user

set -e

# Ensure backup directories have correct permissions
chown -R backup:backup /backups /scripts

# Create log file if it doesn't exist
touch /var/log/cron.log
chmod 666 /var/log/cron.log

# Log startup
echo "$(date): Backup container starting, initializing cron..." >> /var/log/cron.log

# Start crond in the foreground
echo "$(date): Starting crond..." >> /var/log/cron.log
exec crond -f -l 2