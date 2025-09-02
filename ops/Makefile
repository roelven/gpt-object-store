# GPT Object Store Docker Operations Makefile

.PHONY: help build up down test clean logs status backup-test

# Default target
help:
	@echo "GPT Object Store Docker Operations"
	@echo ""
	@echo "Available targets:"
	@echo "  build       - Build all Docker images"
	@echo "  up          - Start all services in detached mode"
	@echo "  down        - Stop and remove all services"
	@echo "  test        - Run Docker setup and log hygiene tests"
	@echo "  clean       - Clean up everything (containers, volumes, images)"
	@echo "  logs        - Show logs for all services"
	@echo "  status      - Show status of all services"
	@echo "  backup-test - Test backup functionality manually"

# Build all images
build:
	docker compose build --no-cache

# Start services
up:
	docker compose up -d

# Stop services
down:
	docker compose down

# Run comprehensive tests
test:
	./test-docker-setup.sh

# Clean up everything
clean:
	docker compose down --volumes --remove-orphans
	docker system prune -f
	docker volume prune -f

# Show logs
logs:
	docker compose logs --follow --tail=100

# Show service status
status:
	docker compose ps
	@echo ""
	@echo "Health status:"
	@docker compose ps --format "table {{.Service}}\t{{.Status}}\t{{.Health}}"

# Test backup functionality
backup-test:
	@echo "Testing backup script manually..."
	docker compose exec backup /scripts/backup.sh
	@echo "Checking backup files..."
	docker compose exec backup ls -la /backups/
	@echo "Verifying backup integrity..."
	docker compose exec backup sh -c 'ls /backups/backup-*.dump | head -1 | xargs pg_restore --list'