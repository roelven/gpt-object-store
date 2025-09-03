# GPT Object Store Docker Operations Makefile

.PHONY: help build up down test clean logs status backup-test
.PHONY: create-gpt create-key list-keys list-gpts revoke-key db-shell db-backup

# Default target
help:
	@echo "GPT Object Store Docker Operations"
	@echo ""
	@echo "Docker Commands:"
	@echo "  build       - Build all Docker images"
	@echo "  up          - Start all services in detached mode"
	@echo "  down        - Stop and remove all services"
	@echo "  test        - Run Docker setup and log hygiene tests"
	@echo "  clean       - Clean up everything (containers, volumes, images)"
	@echo "  logs        - Show logs for all services"
	@echo "  status      - Show status of all services"
	@echo "  backup-test - Test backup functionality manually"
	@echo ""
	@echo "GPT Management Commands:"
	@echo "  create-gpt  - Create a new GPT (usage: make create-gpt ID=my-gpt NAME=\"My GPT\")"
	@echo "  create-key  - Generate API key for a GPT (usage: make create-key GPT_ID=my-gpt)"
	@echo "  list-keys   - List API keys for a GPT (usage: make list-keys GPT_ID=my-gpt)"
	@echo "  list-gpts   - List all GPTs"
	@echo "  revoke-key  - Revoke an API key (usage: make revoke-key KEY=abc123...)"
	@echo ""
	@echo "Database Commands:"
	@echo "  db-shell    - Open PostgreSQL shell"
	@echo "  db-backup   - Create manual database backup"

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

# ===== GPT Management Commands =====

# Create a new GPT
create-gpt:
	@test -n "$(ID)" || (echo "Error: ID is required. Usage: make create-gpt ID=my-gpt NAME=\"My GPT\"" && exit 1)
	@test -n "$(NAME)" || (echo "Error: NAME is required. Usage: make create-gpt ID=my-gpt NAME=\"My GPT\"" && exit 1)
	@docker compose exec -T db psql -U gptstore -d gptstore -c \
		"INSERT INTO gpts (id, name) VALUES ('$(ID)', '$(NAME)') ON CONFLICT (id) DO UPDATE SET name='$(NAME)' RETURNING id, name;" && \
		echo "✓ GPT '$(ID)' created/updated successfully"

# Generate API key for a GPT
create-key:
	@test -n "$(GPT_ID)" || (echo "Error: GPT_ID is required. Usage: make create-key GPT_ID=my-gpt" && exit 1)
	@printf 'import asyncio\nimport sys\nsys.path.append("/app")\nfrom src.auth.api_key import create_api_key\ntry:\n    key = asyncio.run(create_api_key("$(GPT_ID)"))\n    print("")\n    print("==============================================")\n    print("API Key created successfully!")\n    print("==============================================")\n    print(f"API Key: {key}")\n    print("==============================================")\n    print("⚠️  Save this key securely - it cannot be retrieved again")\n    print("")\nexcept Exception as e:\n    print(f"Error: {e}")\n    sys.exit(1)\n' | docker compose exec -T api python

# List API keys for a GPT
list-keys:
	@test -n "$(GPT_ID)" || (echo "Error: GPT_ID is required. Usage: make list-keys GPT_ID=my-gpt" && exit 1)
	@echo "API Keys for GPT '$(GPT_ID)':"
	@docker compose exec -T db psql -U gptstore -d gptstore -t -c \
		"SELECT created_at, last_used FROM api_keys WHERE gpt_id='$(GPT_ID)' ORDER BY created_at DESC;" | \
		sed 's/^[ \t]*//' | grep -v '^$$' || echo "No API keys found for GPT '$(GPT_ID)'"

# List all GPTs
list-gpts:
	@echo "All registered GPTs:"
	@echo "===================="
	@docker compose exec -T db psql -U gptstore -d gptstore -t -c \
		"SELECT id, name, created_at FROM gpts ORDER BY created_at DESC;" | \
		sed 's/^[ \t]*//' | grep -v '^$$' || echo "No GPTs found"

# Revoke an API key
revoke-key:
	@test -n "$(KEY)" || (echo "Error: KEY is required. Usage: make revoke-key KEY=abc123..." && exit 1)
	@docker compose exec api python -c " \
import asyncio; \
import sys; \
sys.path.append('/app'); \
from src.auth.api_key import revoke_api_key; \
try: \
    result = asyncio.run(revoke_api_key('$(KEY)')); \
    if result: \
        print('✓ API key revoked successfully'); \
    else: \
        print('✗ API key not found'); \
        sys.exit(1); \
except Exception as e: \
    print(f'Error: {e}'); \
    sys.exit(1); \
"

# ===== Database Access Commands =====

# Open PostgreSQL shell
db-shell:
	@docker compose exec db psql -U gptstore -d gptstore

# Create manual database backup
db-backup:
	@docker compose exec db pg_dump -U gptstore -Fc gptstore > backup-manual-$$(date +%Y%m%d-%H%M%S).dump
	@echo "✓ Backup saved to backup-manual-$$(date +%Y%m%d-%H%M%S).dump"