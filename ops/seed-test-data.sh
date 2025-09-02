#!/bin/bash
set -euo pipefail

# Test data seeding script for GPT Object Store EVAL.md requirements
# Creates the test data expected by the evaluation script

# Configuration
DB_DSN="${DB_DSN:-postgres://gptstore:change-me@127.0.0.1:5432/gptstore}"
API_BASE="${API_BASE:-http://127.0.0.1:8000/v1}"
API_KEY="${API_KEY:-test-api-key}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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

# Check required tools
for tool in psql curl jq; do
    if ! command -v "$tool" &> /dev/null; then
        log_error "$tool not found. Please install it first."
        exit 1
    fi
done

log_info "Seeding test data for EVAL.md compliance checks..."
log_info "Database: $DB_DSN"
log_info "API Base: $API_BASE"

# Function to execute SQL commands
execute_sql() {
    local sql="$1"
    if ! psql "$DB_DSN" -c "$sql" &>/dev/null; then
        log_error "Failed to execute SQL: $sql"
        return 1
    fi
}

# Function to make API requests
api_request() {
    local method="$1"
    local url="$2"
    local data="${3:-}"
    local headers=(-H "Authorization: Bearer $API_KEY" -H "Accept: application/json")
    
    if [[ -n "$data" ]]; then
        headers+=(-H "Content-Type: application/json" -d "$data")
    fi
    
    curl -s -X "$method" "${headers[@]}" "$API_BASE$url"
}

# Wait for database to be ready
log_info "Waiting for database to be ready..."
for i in {1..30}; do
    if psql "$DB_DSN" -c "SELECT 1" &>/dev/null; then
        log_success "Database is ready"
        break
    fi
    if [[ $i -eq 30 ]]; then
        log_error "Database not ready after 30 attempts"
        exit 1
    fi
    sleep 1
done

# Wait for API to be ready
log_info "Waiting for API to be ready..."
for i in {1..30}; do
    if curl -s "$API_BASE/../health" &>/dev/null; then
        log_success "API is ready"
        break
    fi
    if [[ $i -eq 30 ]]; then
        log_error "API not ready after 30 attempts"
        exit 1
    fi
    sleep 1
done

# Clean existing test data
log_info "Cleaning existing test data..."
execute_sql "DELETE FROM objects WHERE gpt_id IN ('test-gpt', 'other-gpt')"
execute_sql "DELETE FROM collections WHERE gpt_id IN ('test-gpt', 'other-gpt')"
execute_sql "DELETE FROM api_keys WHERE gpt_id IN ('test-gpt', 'other-gpt')"
execute_sql "DELETE FROM gpts WHERE id IN ('test-gpt', 'other-gpt')"

# Create test GPTs
log_info "Creating test GPTs..."
execute_sql "INSERT INTO gpts (id, name, created_at) VALUES ('test-gpt', 'Test GPT', NOW())"
execute_sql "INSERT INTO gpts (id, name, created_at) VALUES ('other-gpt', 'Other GPT', NOW())"

# Create API keys (hashed)
log_info "Creating API keys..."
# Hash for "test-api-key"
TEST_KEY_HASH=$(echo -n "test-api-key" | sha256sum | cut -d' ' -f1)
execute_sql "INSERT INTO api_keys (token_hash, gpt_id, created_at) VALUES (decode('$TEST_KEY_HASH', 'hex'), 'test-gpt', NOW())"

# Hash for "other-api-key" 
OTHER_KEY_HASH=$(echo -n "other-api-key" | sha256sum | cut -d' ' -f1)
execute_sql "INSERT INTO api_keys (token_hash, gpt_id, created_at) VALUES (decode('$OTHER_KEY_HASH', 'hex'), 'other-gpt', NOW())"

# Create test collections via API
log_info "Creating test collections..."

# Create 'notes' collection for test-gpt
notes_collection=$(api_request POST "/gpts/test-gpt/collections" '{
    "name": "notes",
    "schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "content": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "priority": {"type": "integer", "minimum": 1, "maximum": 5}
        },
        "required": ["title"]
    }
}')

if echo "$notes_collection" | jq -e '.name == "notes"' &>/dev/null; then
    log_success "Created 'notes' collection"
else
    log_warning "Notes collection may already exist or creation failed"
fi

# Create 'documents' collection for test-gpt
docs_collection=$(api_request POST "/gpts/test-gpt/collections" '{
    "name": "documents",
    "schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "content": {"type": "string"},
            "type": {"type": "string", "enum": ["pdf", "doc", "txt"]},
            "size": {"type": "integer"}
        },
        "required": ["title", "type"]
    }
}')

if echo "$docs_collection" | jq -e '.name == "documents"' &>/dev/null; then
    log_success "Created 'documents' collection"
else
    log_warning "Documents collection may already exist or creation failed"
fi

# Create test objects for pagination testing
log_info "Creating test objects for pagination..."

# Create objects in 'notes' collection with different timestamps
for i in {1..5}; do
    object_response=$(api_request POST "/gpts/test-gpt/collections/notes/objects" "{
        \"body\": {
            \"title\": \"Test Note $i\",
            \"content\": \"This is the content for test note number $i. It contains some sample text for testing purposes.\",
            \"tags\": [\"test\", \"sample\", \"note$i\"],
            \"priority\": $((i % 5 + 1)),
            \"created_by\": \"seeder\",
            \"sequence\": $i
        }
    }")
    
    if echo "$object_response" | jq -e '.id' &>/dev/null; then
        object_id=$(echo "$object_response" | jq -r '.id')
        log_success "Created object $i: $object_id"
    else
        log_warning "Failed to create object $i"
    fi
    
    # Small delay to ensure different created_at timestamps
    sleep 0.1
done

# Create objects in 'documents' collection
for i in {1..3}; do
    doc_response=$(api_request POST "/gpts/test-gpt/collections/documents/objects" "{
        \"body\": {
            \"title\": \"Document $i\",
            \"content\": \"Content of document $i with some detailed information.\",
            \"type\": \"$([ $((i % 3)) -eq 0 ] && echo 'pdf' || echo 'txt')\",
            \"size\": $((1000 + i * 500)),
            \"author\": \"Test Author\",
            \"version\": \"1.$i\"
        }
    }")
    
    if echo "$doc_response" | jq -e '.id' &>/dev/null; then
        object_id=$(echo "$doc_response" | jq -r '.id')
        log_success "Created document $i: $object_id"
    else
        log_warning "Failed to create document $i"
    fi
    
    sleep 0.1
done

# Create a collection and objects for other-gpt (for isolation testing)
log_info "Creating data for other-gpt (isolation testing)..."

# We need to use the other API key
OTHER_API_KEY="other-api-key"

other_collection=$(curl -s -X POST \
    -H "Authorization: Bearer $OTHER_API_KEY" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d '{"name": "notes", "schema": {"type": "object"}}' \
    "$API_BASE/gpts/other-gpt/collections")

if echo "$other_collection" | jq -e '.name == "notes"' &>/dev/null; then
    log_success "Created collection for other-gpt"
    
    # Create an object for other-gpt
    other_object=$(curl -s -X POST \
        -H "Authorization: Bearer $OTHER_API_KEY" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json" \
        -d '{"body": {"title": "Other GPT Note", "content": "This belongs to other-gpt"}}' \
        "$API_BASE/gpts/other-gpt/collections/notes/objects")
    
    if echo "$other_object" | jq -e '.id' &>/dev/null; then
        log_success "Created object for other-gpt"
    fi
fi

# Verify seeded data
log_info "Verifying seeded data..."

# Check collections count
collections_response=$(api_request GET "/gpts/test-gpt/collections")
collections_count=$(echo "$collections_response" | jq -r '.collections | length')
log_info "Created $collections_count collections for test-gpt"

# Check objects count in notes collection
notes_objects_response=$(api_request GET "/gpts/test-gpt/collections/notes/objects?limit=100")
notes_count=$(echo "$notes_objects_response" | jq -r '.objects | length')
log_info "Created $notes_count objects in notes collection"

# Check objects count in documents collection
docs_objects_response=$(api_request GET "/gpts/test-gpt/collections/documents/objects?limit=100")
docs_count=$(echo "$docs_objects_response" | jq -r '.objects | length')
log_info "Created $docs_count objects in documents collection"

# Verify database state
log_info "Database verification:"
gpts_count=$(psql "$DB_DSN" -t -c "SELECT COUNT(*) FROM gpts WHERE id LIKE 'test-%' OR id LIKE 'other-%'" | xargs)
api_keys_count=$(psql "$DB_DSN" -t -c "SELECT COUNT(*) FROM api_keys WHERE gpt_id LIKE 'test-%' OR gpt_id LIKE 'other-%'" | xargs)
collections_count=$(psql "$DB_DSN" -t -c "SELECT COUNT(*) FROM collections WHERE gpt_id LIKE 'test-%' OR gpt_id LIKE 'other-%'" | xargs)
objects_count=$(psql "$DB_DSN" -t -c "SELECT COUNT(*) FROM objects WHERE gpt_id LIKE 'test-%' OR gpt_id LIKE 'other-%'" | xargs)

log_info "  GPTs: $gpts_count"
log_info "  API Keys: $api_keys_count"
log_info "  Collections: $collections_count"
log_info "  Objects: $objects_count"

# Create additional test scenarios data
log_info "Creating additional test scenario data..."

# Create objects for rate limiting test (if needed)
log_info "Creating additional objects for comprehensive testing..."

# Create some objects with known IDs for update/delete testing
known_object=$(api_request POST "/gpts/test-gpt/collections/notes/objects" '{
    "body": {
        "title": "Known Test Object",
        "content": "This object will be used for update and delete testing",
        "test_marker": "known_object",
        "modifiable": true
    }
}')

if echo "$known_object" | jq -e '.id' &>/dev/null; then
    known_id=$(echo "$known_object" | jq -r '.id')
    log_success "Created known test object: $known_id"
    
    # Store the ID for later use
    echo "$known_id" > /tmp/known_test_object_id.txt
fi

# Summary
log_success "Test data seeding completed successfully!"
log_info "Summary of seeded data:"
log_info "  - Created test-gpt and other-gpt"
log_info "  - Created API keys for both GPTs"
log_info "  - Created 'notes' and 'documents' collections"
log_info "  - Created multiple objects for pagination testing"
log_info "  - Created isolation test data"
log_info ""
log_info "The following environment variables are set for EVAL.md:"
log_info "  DB_DSN=$DB_DSN"
log_info "  API_BASE=$API_BASE"  
log_info "  API_KEY=$API_KEY"
log_info ""
log_info "You can now run the evaluation script to validate compliance."