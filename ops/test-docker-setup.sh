#!/bin/bash

# GPT Object Store Docker Compose Setup Test Script
# Tests that the Docker Compose setup works correctly and performs log hygiene checks

set -euo pipefail

# Configuration
PROJECT_ROOT="/Users/roel/Code/gpt-object-store"
COMPOSE_FILE="$PROJECT_ROOT/ops/compose.yml"
TEST_TIMEOUT=120
HEALTH_CHECK_TIMEOUT=60
LOG_CHECK_DURATION=30

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Test results tracking
TESTS_PASSED=0
TESTS_FAILED=0

test_result() {
    local test_name="$1"
    local result="$2"
    
    if [ "$result" = "PASS" ]; then
        log_info "✅ $test_name"
        ((TESTS_PASSED++))
    else
        log_error "❌ $test_name"
        ((TESTS_FAILED++))
    fi
}

# Cleanup function
cleanup() {
    log_info "Cleaning up Docker Compose services..."
    cd "$PROJECT_ROOT/ops"
    docker compose down --volumes --remove-orphans 2>/dev/null || true
    docker system prune -f 2>/dev/null || true
}

# Set trap for cleanup
trap cleanup EXIT

# Main test function
main() {
    log_info "Starting GPT Object Store Docker Compose Tests"
    log_info "Project root: $PROJECT_ROOT"
    log_info "Compose file: $COMPOSE_FILE"
    
    # Change to ops directory
    cd "$PROJECT_ROOT/ops"
    
    # Test 1: Compose file validation
    log_info "Test 1: Validating Docker Compose file..."
    if docker compose config > /dev/null 2>&1; then
        test_result "Docker Compose file validation" "PASS"
    else
        test_result "Docker Compose file validation" "FAIL"
        log_error "Docker Compose file is invalid"
        return 1
    fi
    
    # Test 2: Build services
    log_info "Test 2: Building Docker images..."
    if timeout $TEST_TIMEOUT docker compose build --no-cache; then
        test_result "Docker images build" "PASS"
    else
        test_result "Docker images build" "FAIL"
        log_error "Failed to build Docker images"
        return 1
    fi
    
    # Test 3: Start services
    log_info "Test 3: Starting services in detached mode..."
    if docker compose up -d; then
        test_result "Services startup" "PASS"
    else
        test_result "Services startup" "FAIL"
        log_error "Failed to start services"
        return 1
    fi
    
    # Test 4: Wait for services to be healthy
    log_info "Test 4: Waiting for services to become healthy..."
    local healthy_services=0
    local expected_services=3
    
    for i in $(seq 1 $HEALTH_CHECK_TIMEOUT); do
        healthy_services=$(docker compose ps --format json | jq -r '.Health // "healthy"' | grep -c "healthy" || echo "0")
        
        if [ "$healthy_services" -eq "$expected_services" ]; then
            break
        fi
        
        log_info "Health check $i/$HEALTH_CHECK_TIMEOUT: $healthy_services/$expected_services services healthy"
        sleep 2
    done
    
    if [ "$healthy_services" -eq "$expected_services" ]; then
        test_result "All services healthy" "PASS"
    else
        test_result "All services healthy" "FAIL"
        log_error "Only $healthy_services/$expected_services services are healthy"
        docker compose ps
    fi
    
    # Test 5: Check service connectivity
    log_info "Test 5: Testing service connectivity..."
    
    # Test database connectivity
    if docker compose exec -T db pg_isready -U gptstore -d gptstore; then
        test_result "Database connectivity" "PASS"
    else
        test_result "Database connectivity" "FAIL"
    fi
    
    # Test API health endpoint (assuming it exists)
    local api_health_result=0
    for i in $(seq 1 10); do
        if curl -f -s http://localhost:8000/health > /dev/null 2>&1; then
            api_health_result=1
            break
        fi
        sleep 2
    done
    
    if [ "$api_health_result" -eq 1 ]; then
        test_result "API health endpoint" "PASS"
    else
        test_result "API health endpoint" "FAIL"
    fi
    
    # Test 6: Log hygiene check
    log_info "Test 6: Checking logs for error patterns during $LOG_CHECK_DURATION seconds..."
    
    # Wait a bit for services to settle
    sleep $LOG_CHECK_DURATION
    
    # Define forbidden log patterns (case-insensitive)
    local forbidden_patterns=(
        "FATAL"
        "CRITICAL" 
        "ERROR.*failed"
        "ERROR.*connection.*refused"
        "ERROR.*timeout"
        "panic"
        "segmentation fault"
        "out of memory"
        "permission denied"
        "no such file"
        "cannot connect"
        "authentication failed"
        "access denied"
    )
    
    local log_errors_found=0
    
    for service in db api backup; do
        log_info "Checking logs for service: $service"
        local service_logs
        service_logs=$(docker compose logs "$service" 2>&1)
        
        for pattern in "${forbidden_patterns[@]}"; do
            if echo "$service_logs" | grep -qi "$pattern"; then
                log_error "Found forbidden pattern '$pattern' in $service logs"
                echo "$service_logs" | grep -i "$pattern"
                ((log_errors_found++))
            fi
        done
    done
    
    if [ "$log_errors_found" -eq 0 ]; then
        test_result "Log hygiene check" "PASS"
    else
        test_result "Log hygiene check" "FAIL"
        log_error "Found $log_errors_found forbidden log patterns"
    fi
    
    # Test 7: Backup service functionality
    log_info "Test 7: Testing backup service functionality..."
    
    # Check if cron is running in backup container
    if docker compose exec -T backup pgrep crond > /dev/null; then
        test_result "Backup cron service running" "PASS"
    else
        test_result "Backup cron service running" "FAIL"
    fi
    
    # Check if backup script is executable and valid
    if docker compose exec -T backup test -x /scripts/backup.sh; then
        test_result "Backup script executable" "PASS"
    else
        test_result "Backup script executable" "FAIL"
    fi
    
    # Test 8: Volume persistence
    log_info "Test 8: Testing volume persistence..."
    
    # Check if named volumes exist
    local db_volume_exists=0
    local backup_volume_exists=0
    
    if docker volume ls | grep -q "ops_db-data"; then
        db_volume_exists=1
    fi
    
    if docker volume ls | grep -q "ops_db-backups"; then
        backup_volume_exists=1
    fi
    
    if [ "$db_volume_exists" -eq 1 ] && [ "$backup_volume_exists" -eq 1 ]; then
        test_result "Named volumes created" "PASS"
    else
        test_result "Named volumes created" "FAIL"
    fi
    
    # Display final results
    log_info "==================== TEST SUMMARY ===================="
    log_info "Tests passed: $TESTS_PASSED"
    log_info "Tests failed: $TESTS_FAILED"
    log_info "Total tests: $((TESTS_PASSED + TESTS_FAILED))"
    
    if [ "$TESTS_FAILED" -eq 0 ]; then
        log_info "🎉 All tests passed! Docker Compose setup is working correctly."
        return 0
    else
        log_error "❌ $TESTS_FAILED tests failed. Please check the logs above."
        return 1
    fi
}

# Run main function
main "$@"