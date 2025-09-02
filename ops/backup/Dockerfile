FROM postgres:17-alpine

# Install additional packages needed for backup
RUN apk add --no-cache \
    bash \
    curl \
    findutils

# Create backup user and directories
RUN addgroup -g 1001 backup && \
    adduser -D -u 1001 -G backup backup && \
    mkdir -p /backups /scripts /var/log && \
    chown -R backup:backup /backups /scripts

# Copy backup scripts
COPY --chown=backup:backup backup.sh /scripts/backup.sh
COPY --chown=root:root run-backup.sh /scripts/run-backup.sh

# Make scripts executable
RUN chmod +x /scripts/backup.sh /scripts/run-backup.sh

# Create log file with proper permissions
RUN touch /var/log/cron.log && \
    chmod 666 /var/log/cron.log

# Set working directory
WORKDIR /backups

# Health check - verify backup scheduler is running
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ps aux | grep -v grep | grep -q run-backup.sh || exit 1

# Run the backup scheduler
CMD ["/scripts/run-backup.sh"]