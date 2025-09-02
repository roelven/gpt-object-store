FROM alpine:3.18

# Install required packages
RUN apk add --no-cache \
    postgresql-client \
    bash \
    curl \
    findutils

# Create backup user and directories
RUN addgroup -g 1001 backup && \
    adduser -D -u 1001 -G backup backup && \
    mkdir -p /backups /scripts /var/log && \
    chown -R backup:backup /backups /scripts

# Copy scripts and configuration
COPY --chown=backup:backup backup.sh /scripts/backup.sh
COPY --chown=root:root crontab /etc/crontabs/root
COPY --chown=root:root entrypoint.sh /entrypoint.sh

# Make scripts executable
RUN chmod +x /scripts/backup.sh /entrypoint.sh && \
    chmod 0600 /etc/crontabs/root

# Create log file with proper permissions
RUN touch /var/log/cron.log && \
    chmod 666 /var/log/cron.log

# Set working directory
WORKDIR /backups

# Health check - verify cron is running
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD pgrep crond > /dev/null || exit 1

# Use entrypoint script to start cron
ENTRYPOINT ["/entrypoint.sh"]