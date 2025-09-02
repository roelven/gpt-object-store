#!/bin/bash
set -euo pipefail

# Comprehensive evaluation script for GPT Object Store EVAL.md compliance
# Validates all requirements and generates a PASS/FAIL report

# Configuration
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
DB_DSN="${DB_DSN:-postgres://gptstore:change-me@127.0.0.1:5432/gptstore}"
API_BASE="${API_BASE:-http://127.0.0.1:8000/v1}"
API_KEY="${API_KEY:-test-api-key}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

# Test results tracking
declare -A RESULTS
TOTAL_TESTS=0
PASSED_TESTS=0

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_header() {
    echo -e "\n${BOLD}${BLUE}=== $1 ===${NC}"
}

# Record test result
record_result() {
    local test_name="$1"
    local result="$2"  # PASS or FAIL
    local details="${3:-}"
    
    RESULTS["$test_name"]="$result"
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    if [[ "$result" == "PASS" ]]; then
        PASSED_TESTS=$((PASSED_TESTS + 1))
        log_success "$test_name: PASS"
    else
        log_error "$test_name: FAIL"
    fi
    
    if [[ -n "$details" ]]; then
        echo "  Details: $details"
    fi
}

# Check if command exists
check_command() {
    if ! command -v "$1" &> /dev/null; then
        log_error "$1 not found. Please install it first."
        exit 1
    fi
}

# Check required tools
log_info "Checking required tools..."
for tool in psql curl jq grep find awk; do
    check_command "$tool"
done

log_header "GPT Object Store EVAL.md Compliance Check"
log_info "Repository: $REPO_ROOT"
log_info "Database: $DB_DSN"
log_info "API Base: $API_BASE"

# Test 1: Data model (DDL) JSONB, multi-GPT, collections first-class
log_header "1. Data Model and Schema Validation"

# Check tables exist
if psql "$DB_DSN" -c "\dt+" &>/dev/null; then
    tables=$(psql "$DB_DSN" -t -c "\dt" | awk '{print $3}' | grep -E '^(gpts|api_keys|collections|objects)$' | wc -l)
    if [[ $tables -eq 4 ]]; then
        record_result "Tables exist" "PASS"
    else
        record_result "Tables exist" "FAIL" "Expected 4 tables (gpts, api_keys, collections, objects), found $tables"
    fi
else
    record_result "Database connectivity" "FAIL" "Cannot connect to database"
fi

# Check objects.body is JSONB
body_type=$(psql "$DB_DSN" -t -c "SELECT data_type FROM information_schema.columns WHERE table_name = 'objects' AND column_name = 'body'" | xargs)
if [[ "$body_type" == "jsonb" ]]; then
    record_result "Objects body is JSONB" "PASS"
else
    record_result "Objects body is JSONB" "FAIL" "Found: $body_type"
fi

# Check GIN index on body exists
gin_indexes=$(psql "$DB_DSN" -t -c "SELECT COUNT(*) FROM pg_indexes WHERE tablename = 'objects' AND indexdef LIKE '%gin%body%'" | xargs)
if [[ $gin_indexes -gt 0 ]]; then
    record_result "GIN index on body" "PASS"
else
    record_result "GIN index on body" "FAIL" "No GIN index found on objects.body"
fi

# Check composite index
composite_indexes=$(psql "$DB_DSN" -t -c "SELECT COUNT(*) FROM pg_indexes WHERE tablename = 'objects' AND indexdef LIKE '%gpt_id%collection%created_at%'" | xargs)
if [[ $composite_indexes -gt 0 ]]; then
    record_result "Composite index (gpt_id, collection, created_at)" "PASS"
else
    record_result "Composite index (gpt_id, collection, created_at)" "FAIL" "Required composite index not found"
fi

# Test 2: Postgres-only enforcement
log_header "2. PostgreSQL-Only Enforcement"

sqlite_refs=$(grep -R -i "sqlite" "$REPO_ROOT" 2>/dev/null | wc -l || echo 0)
if [[ $sqlite_refs -eq 0 ]]; then
    record_result "No SQLite references" "PASS"
else
    record_result "No SQLite references" "FAIL" "Found $sqlite_refs SQLite references"
fi

sqlite3_refs=$(grep -R -i "sqlite3" "$REPO_ROOT" 2>/dev/null | wc -l || echo 0)
if [[ $sqlite3_refs -eq 0 ]]; then
    record_result "No SQLite3 references" "PASS"
else
    record_result "No SQLite3 references" "FAIL" "Found $sqlite3_refs SQLite3 references"
fi

# Test 3: API surface (OpenAPI 3.1) Actions-ready, OAuth-ready
log_header "3. OpenAPI 3.1 Specification"

openapi_file="$REPO_ROOT/api/openapi/gpt-object-store.yaml"
if [[ -f "$openapi_file" ]]; then
    record_result "OpenAPI file exists" "PASS"
    
    # Check version
    if grep -E "openapi:\s*3\.1" "$openapi_file" &>/dev/null; then
        record_result "OpenAPI version 3.1" "PASS"
    else
        record_result "OpenAPI version 3.1" "FAIL" "Not OpenAPI 3.1"
    fi
    
    # Check security schemes
    if grep -E "securitySchemes:" "$openapi_file" &>/dev/null; then
        if grep -A 20 "securitySchemes:" "$openapi_file" | grep -E "(bearer|Bearer)" &>/dev/null; then
            record_result "Bearer security scheme" "PASS"
        else
            record_result "Bearer security scheme" "FAIL" "Bearer scheme not found"
        fi
        
        if grep -A 20 "securitySchemes:" "$openapi_file" | grep -E "oauth2" &>/dev/null; then
            record_result "OAuth2 security scheme" "PASS"
        else
            record_result "OAuth2 security scheme" "FAIL" "OAuth2 scheme not found"
        fi
    else
        record_result "Security schemes defined" "FAIL" "No securitySchemes found"
    fi
    
    # Check object endpoints
    if grep -E "/gpts/\{gpt_id\}/collections/\{name\}/objects:" "$openapi_file" &>/dev/null; then
        record_result "Object endpoints defined" "PASS"
    else
        record_result "Object endpoints defined" "FAIL" "Object endpoints not found in OpenAPI"
    fi
else
    record_result "OpenAPI file exists" "FAIL" "File not found: $openapi_file"
fi

# Test 4: Auth now and later Bearer header, OAuth-ready
log_header "4. Authentication"

# Check API keys table structure
api_keys_structure=$(psql "$DB_DSN" -c "\d+ api_keys" 2>/dev/null | grep token_hash | wc -l)
if [[ $api_keys_structure -gt 0 ]]; then
    record_result "API keys stored as hash" "PASS"
else
    record_result "API keys stored as hash" "FAIL" "token_hash column not found"
fi

# Test authentication required
auth_response=$(curl -s -o /dev/null -w "%{http_code}" "$API_BASE/gpts/test-gpt/collections")
if [[ "$auth_response" == "401" ]]; then
    record_result "Authentication required" "PASS"
else
    record_result "Authentication required" "FAIL" "Expected 401, got $auth_response"
fi

# Test 5: Pagination required seek or keyset and Link headers
log_header "5. Pagination Implementation"

# Create test objects for pagination
log_info "Creating test objects for pagination test..."
for i in {1..3}; do
    curl -s -X POST "$API_BASE/gpts/test-gpt/collections/notes/objects" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d "{\"body\":{\"m\":$i}}" >/dev/null
    sleep 0.1
done

# Test pagination response
pagination_response=$(curl -s -i "$API_BASE/gpts/test-gpt/collections/notes/objects?limit=1&order=desc" \
    -H "Authorization: Bearer $API_KEY" \
    -H "Accept: application/json")

# Check for Link header
if echo "$pagination_response" | grep -E "^Link: .*rel=\"next\"" &>/dev/null; then
    record_result "Link header with rel=next" "PASS"
else
    record_result "Link header with rel=next" "FAIL" "Link header not found"
fi

# Check for next_cursor in response body
response_body=$(echo "$pagination_response" | awk '/^\{/{flag=1} flag{print}')
if echo "$response_body" | jq -e '.next_cursor' &>/dev/null; then
    record_result "next_cursor in response" "PASS"
else
    record_result "next_cursor in response" "FAIL" "next_cursor not found in response"
fi

# Test cursor-based pagination
next_cursor=$(echo "$response_body" | jq -r '.next_cursor // empty')
if [[ -n "$next_cursor" ]]; then
    page2_response=$(curl -s "$API_BASE/gpts/test-gpt/collections/notes/objects?limit=1&cursor=$next_cursor" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Accept: application/json")
    
    if echo "$page2_response" | jq -e '.objects' &>/dev/null; then
        record_result "Cursor-based pagination works" "PASS"
    else
        record_result "Cursor-based pagination works" "FAIL" "Second page request failed"
    fi
fi

# Test 6: Collections as first-class and multi-GPT scoping
log_header "6. Collections and Multi-GPT Scoping"

# Test collection creation (idempotent)
collection_create=$(curl -s -X POST "$API_BASE/gpts/test-gpt/collections" \
    -H "Authorization: Bearer $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"name":"notes"}')

if echo "$collection_create" | jq -e '.name == "notes"' &>/dev/null || [[ $(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_BASE/gpts/test-gpt/collections" -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" -d '{"name":"notes"}') == "409" ]]; then
    record_result "Collection creation idempotent" "PASS"
else
    record_result "Collection creation idempotent" "FAIL" "Collection creation not properly handled"
fi

# Test cross-GPT access denied
cross_gpt_response=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $API_KEY" \
    "$API_BASE/gpts/other-gpt/collections/notes/objects?limit=1")

if [[ "$cross_gpt_response" == "404" || "$cross_gpt_response" == "403" ]]; then
    record_result "Cross-GPT access denied" "PASS"
else
    record_result "Cross-GPT access denied" "FAIL" "Expected 403/404, got $cross_gpt_response"
fi

# Test 7: Error format Problem Details (RFC 9457)
log_header "7. Problem Details Error Format"

# Test 401 error format
error_401=$(curl -s -i "$API_BASE/gpts/test-gpt/collections" -H "Accept: application/json")
if echo "$error_401" | grep -i "Content-Type: application/problem+json" &>/dev/null; then
    record_result "401 returns Problem Details" "PASS"
else
    record_result "401 returns Problem Details" "FAIL" "Not using application/problem+json"
fi

# Test error structure
error_body=$(echo "$error_401" | awk '/^\{/{flag=1} flag{print}')
if echo "$error_body" | jq -e '.type and .title and .status' &>/dev/null; then
    record_result "Problem Details structure" "PASS"
else
    record_result "Problem Details structure" "FAIL" "Missing required fields (type, title, status)"
fi

# Test 8: Rate limits sensible caps and Retry-After
log_header "8. Rate Limiting"

log_info "Testing rate limiting (may take a moment)..."
rate_limit_hit=false

for i in $(seq 1 80); do
    response_code=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $API_KEY" \
        "$API_BASE/gpts/test-gpt/collections")
    
    if [[ "$response_code" == "429" ]]; then
        rate_limit_hit=true
        
        # Check for Retry-After header
        retry_after=$(curl -s -i -H "Authorization: Bearer $API_KEY" \
            "$API_BASE/gpts/test-gpt/collections" | grep -i "Retry-After:" | cut -d' ' -f2)
        
        if [[ -n "$retry_after" ]]; then
            record_result "Rate limiting with Retry-After" "PASS"
        else
            record_result "Rate limiting with Retry-After" "FAIL" "429 but no Retry-After header"
        fi
        break
    fi
done

if [[ "$rate_limit_hit" == "false" ]]; then
    record_result "Rate limiting triggers" "FAIL" "Rate limit not reached in 80 requests"
fi

# Test 9: Nightly backups pg_dump plus rotation
log_header "9. Backup Configuration"

if grep -r "pg_dump" "$REPO_ROOT/ops/backup" &>/dev/null; then
    record_result "pg_dump backup configured" "PASS"
else
    record_result "pg_dump backup configured" "FAIL" "pg_dump not found in backup config"
fi

if grep -r "crond" "$REPO_ROOT/ops/backup" &>/dev/null; then
    record_result "Cron daemon configured" "PASS"
else
    record_result "Cron daemon configured" "FAIL" "crond not found in backup config"
fi

# Test 10: Docker Compose bring-up and log hygiene
log_header "10. Docker Compose and Log Hygiene"

compose_file="$REPO_ROOT/ops/compose.yml"
if [[ -f "$compose_file" ]]; then
    record_result "Docker Compose file exists" "PASS"
    
    # Check for required services
    if grep -E "^\s*(db|api|backup):" "$compose_file" &>/dev/null; then
        record_result "Required services defined" "PASS"
    else
        record_result "Required services defined" "FAIL" "Missing required services (db, api, backup)"
    fi
else
    record_result "Docker Compose file exists" "FAIL" "File not found: $compose_file"
fi

# Test 11: Endpoint behavior CRUD sanity
log_header "11. CRUD Operations"

# Create object
object_id=$(curl -s -X POST "$API_BASE/gpts/test-gpt/collections/notes/objects" \
    -H "Authorization: Bearer $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"body":{"a":1}}' | jq -r '.id // empty')

if [[ -n "$object_id" ]]; then
    record_result "Object creation (POST)" "PASS"
    
    # Read object
    read_response=$(curl -s "$API_BASE/objects/$object_id" -H "Authorization: Bearer $API_KEY")
    if echo "$read_response" | jq -e '.body.a == 1' &>/dev/null; then
        record_result "Object retrieval (GET)" "PASS"
    else
        record_result "Object retrieval (GET)" "FAIL" "Object not retrieved correctly"
    fi
    
    # Update object
    original_updated_at=$(echo "$read_response" | jq -r '.updated_at')
    sleep 0.1  # Ensure timestamp difference
    
    update_response=$(curl -s -X PATCH "$API_BASE/objects/$object_id" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d '{"body":{"a":2}}')
    
    new_updated_at=$(echo "$update_response" | jq -r '.updated_at // empty')
    if [[ "$new_updated_at" > "$original_updated_at" ]]; then
        record_result "Object update (PATCH)" "PASS"
    else
        record_result "Object update (PATCH)" "FAIL" "updated_at not changed"
    fi
    
    # Delete object
    delete_response=$(curl -s -o /dev/null -w "%{http_code}" \
        -X DELETE -H "Authorization: Bearer $API_KEY" \
        "$API_BASE/objects/$object_id")
    
    if [[ "$delete_response" == "204" ]]; then
        record_result "Object deletion (DELETE)" "PASS"
    else
        record_result "Object deletion (DELETE)" "FAIL" "Expected 204, got $delete_response"
    fi
else
    record_result "Object creation (POST)" "FAIL" "Failed to create object"
fi

# Test 12: Repo hygiene and tests
log_header "12. Repository and Test Hygiene"

# Run tests and check pass rate
log_info "Running test suite..."
if [[ -f "$REPO_ROOT/api/tests/test_runner.sh" ]]; then
    if cd "$REPO_ROOT/api" && timeout 12s bash tests/test_runner.sh >/tmp/test_run_output.txt 2>&1; then
        test_pass_rate=$(grep "RATE=" /tmp/test_run_output.txt | tail -1 | sed 's/.*RATE=\([0-9.]*\)%.*/\1/')
        
        if [[ -n "$test_pass_rate" ]] && (( $(echo "$test_pass_rate >= 90" | bc -l 2>/dev/null || python3 -c "print(int($test_pass_rate >= 90))") )); then
            record_result "Test pass rate ≥90%" "PASS" "Pass rate: ${test_pass_rate}%"
        else
            record_result "Test pass rate ≥90%" "FAIL" "Pass rate: ${test_pass_rate}%"
        fi
        
        record_result "Tests complete within 10s" "PASS"
    else
        record_result "Tests complete within 10s" "FAIL" "Tests timed out or failed"
        record_result "Test pass rate ≥90%" "FAIL" "Could not determine pass rate"
    fi
else
    record_result "Test runner exists" "FAIL" "test_runner.sh not found"
fi

# Check file length requirements (≤300 lines)
oversized_files=$(find "$REPO_ROOT" -type f \( -name "*.py" -o -name "*.ts" \) -exec wc -l {} \; | awk '$1>300{print $2}' | wc -l)
if [[ $oversized_files -eq 0 ]]; then
    record_result "File length ≤300 lines" "PASS"
else
    record_result "File length ≤300 lines" "FAIL" "$oversized_files files exceed 300 lines"
fi

# Test 13: Security header and media type checks
log_header "13. Security and Media Types"

# Auth required yields 401
auth_check=$(curl -s -i "$API_BASE/gpts/test-gpt/collections/notes/objects?limit=1" | head -1)
if echo "$auth_check" | grep -E "HTTP/[12](\.[01])? 401" &>/dev/null; then
    record_result "401 for missing auth" "PASS"
else
    record_result "401 for missing auth" "FAIL" "Did not return 401 for missing auth"
fi

# Problem Details content type for errors
error_content_type=$(curl -s -i "$API_BASE/gpts/test-gpt/collections/notes/objects?cursor=bad==" \
    -H "Authorization: Bearer $API_KEY" | grep -i "Content-Type:" | grep "application/problem+json")

if [[ -n "$error_content_type" ]]; then
    record_result "Problem Details content type" "PASS"
else
    record_result "Problem Details content type" "FAIL" "Errors not using application/problem+json"
fi

# Test 14: Git discipline
log_header "14. Git Discipline"

# Check working tree is clean
if git -C "$REPO_ROOT" status --porcelain | grep -q .; then
    record_result "Clean working tree" "FAIL" "Uncommitted changes found"
else
    record_result "Clean working tree" "PASS"
fi

# Check for required commit footer
if git -C "$REPO_ROOT" log -n 30 --pretty=%B | grep -E "Generated with.*Claude Code" -q; then
    record_result "Required commit footer" "PASS"
else
    record_result "Required commit footer" "FAIL" "Required footer not found in recent commits"
fi

# Generate final report
log_header "EVALUATION SUMMARY"

echo ""
echo "INDIVIDUAL TEST RESULTS:"
echo "========================"

for test_name in "${!RESULTS[@]}"; do
    result="${RESULTS[$test_name]}"
    if [[ "$result" == "PASS" ]]; then
        echo -e "✓ ${GREEN}$test_name: $result${NC}"
    else
        echo -e "✗ ${RED}$test_name: $result${NC}"
    fi
done

echo ""
echo "OVERALL SUMMARY:"
echo "================"
echo "Total tests: $TOTAL_TESTS"
echo "Passed: $PASSED_TESTS"
echo "Failed: $((TOTAL_TESTS - PASSED_TESTS))"

pass_percentage=$(python3 -c "print(f'{100.0 * $PASSED_TESTS / $TOTAL_TESTS:.1f}')")
echo "Pass rate: ${pass_percentage}%"

# Determine overall result
critical_tests=(
    "Tables exist"
    "Objects body is JSONB" 
    "OpenAPI file exists"
    "Authentication required"
    "Link header with rel=next"
    "Problem Details structure"
    "Test pass rate ≥90%"
)

critical_failures=0
for test in "${critical_tests[@]}"; do
    if [[ "${RESULTS[$test]:-FAIL}" == "FAIL" ]]; then
        critical_failures=$((critical_failures + 1))
    fi
done

echo ""
if [[ $critical_failures -eq 0 ]] && (( $(echo "$pass_percentage >= 85" | bc -l 2>/dev/null || python3 -c "print(int($pass_percentage >= 85))") )); then
    echo -e "${BOLD}${GREEN}OVERALL RESULT: PASS${NC}"
    echo "The GPT Object Store meets all critical requirements and achieves ≥85% overall compliance."
    exit 0
else
    echo -e "${BOLD}${RED}OVERALL RESULT: FAIL${NC}"
    echo "Critical failures: $critical_failures"
    echo "The GPT Object Store does not meet the minimum requirements for compliance."
    exit 1
fi