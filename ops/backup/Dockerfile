FROM alpine:3.18

# Install required packages
RUN apk add --no-cache \
    postgresql-client \
    dcron \
    bash \
    curl \
    findutils

# Create backup user and directories
RUN addgroup -g 1001 backup && \
    adduser -D -u 1001 -G backup backup && \
    mkdir -p /backups /scripts /var/log && \
    chown -R backup:backup /backups /scripts /var/log

# Copy scripts and configuration
COPY backup.sh /scripts/backup.sh
COPY crontab /tmp/crontab

# Make scripts executable and set up cron
RUN chmod +x /scripts/backup.sh && \
    crontab -u backup /tmp/crontab && \
    rm /tmp/crontab

# Create log file for cron
RUN touch /var/log/cron.log && \
    chown backup:backup /var/log/cron.log

# Switch to backup user
USER backup

# Create initial log entries
RUN echo "$(date): Backup container initialized" >> /var/log/cron.log

# Set working directory
WORKDIR /backups

# Health check - verify cron is running and log file exists
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD test -f /var/log/cron.log && pgrep crond > /dev/null

# Start cron in foreground with logging
CMD ["sh", "-c", "crond -f -L /var/log/cron.log"]