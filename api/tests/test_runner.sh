#!/bin/bash
set -euo pipefail

# Test runner script with timing validation for GPT Object Store API
# Ensures tests complete within 10 seconds and achieve ≥90% pass rate

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$(dirname "$SCRIPT_DIR")"
ROOT_DIR="$(dirname "$API_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
MAX_TEST_TIME=10
MIN_PASS_RATE=90.0
TEST_OUTPUT_FILE="/tmp/gpt_object_store_test_output.txt"
COVERAGE_REPORT="/tmp/gpt_object_store_coverage.txt"

# Helper functions
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

# Check if we're in the right directory
if [[ ! -f "$API_DIR/pytest.ini" ]]; then
    log_error "pytest.ini not found. Please run this script from the api/tests directory."
    exit 1
fi

# Change to API directory for test execution
cd "$API_DIR"

log_info "Starting GPT Object Store API test suite..."
log_info "API Directory: $API_DIR"
log_info "Maximum test time: ${MAX_TEST_TIME}s"
log_info "Minimum pass rate: ${MIN_PASS_RATE}%"

# Check for required tools
if ! command -v pytest &> /dev/null; then
    log_error "pytest not found. Please install development dependencies:"
    log_error "pip install -r requirements-dev.txt"
    exit 1
fi

# Clean up previous test artifacts
rm -f "$TEST_OUTPUT_FILE" "$COVERAGE_REPORT"
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
rm -f .coverage

# Run tests with timing
log_info "Running tests with timeout enforcement..."

start_time=$(date +%s.%3N)

# Run pytest with timeout and capture output
if timeout ${MAX_TEST_TIME}s pytest tests/ \
    --tb=short \
    --disable-warnings \
    --timeout=10 \
    --cov=src \
    --cov-report=term-missing \
    --cov-report=term \
    -v 2>&1 | tee "$TEST_OUTPUT_FILE"; then
    
    test_exit_code=0
else
    test_exit_code=$?
fi

end_time=$(date +%s.%3N)
elapsed_time=$(echo "$end_time - $start_time" | bc -l 2>/dev/null || python3 -c "print($end_time - $start_time)")

log_info "Test execution completed in ${elapsed_time}s"

# Check if tests timed out
if [[ $test_exit_code -eq 124 ]]; then
    log_error "Tests exceeded maximum time limit of ${MAX_TEST_TIME}s"
    exit 1
fi

# Validate execution time
if (( $(echo "$elapsed_time > $MAX_TEST_TIME" | bc -l 2>/dev/null || python3 -c "print(int($elapsed_time > $MAX_TEST_TIME))") )); then
    log_warning "Tests completed but took longer than ${MAX_TEST_TIME}s: ${elapsed_time}s"
else
    log_success "Tests completed within time limit: ${elapsed_time}s"
fi

# Parse test results for pass rate calculation
log_info "Analyzing test results..."

# Strategy A: pytest-style summary (preferred)
if grep -E "(passed|failed|errors)" "$TEST_OUTPUT_FILE" | tail -1 | grep -q "passed\|failed\|errors"; then
    test_summary=$(grep -E "(passed|failed|errors)" "$TEST_OUTPUT_FILE" | tail -1)
    log_info "Test summary: $test_summary"
    
    # Extract numbers using awk
    pass_rate=$(awk '
        /passed,|failed,|errors,/ {
            for (i=1;i<=NF;i++){
                if ($i ~ /passed,?/){sub(/,/, "", $i); split($i,a,"passed"); p=a[1]}
                if ($i ~ /failed,?/){sub(/,/, "", $i); split($i,a,"failed"); f=a[1]}
                if ($i ~ /errors,?/){sub(/,/, "", $i); split($i,a,"errors"); e=a[1]}
            }
        }
        END {
            if (p=="" && f=="" && e=="") { exit 2 }
            p = (p == "") ? 0 : p
            f = (f == "") ? 0 : f  
            e = (e == "") ? 0 : e
            total = p + f + e
            rate = (total>0) ? (100.0 * p / total) : 0
            printf("TOTAL=%d PASSED=%d FAILED=%d ERRORS=%d RATE=%.2f%%\n", total, p, f, e, rate);
            printf("%.2f", rate);
        }
    ' "$TEST_OUTPUT_FILE")

# Strategy B: fallback - count PASSED/FAILED patterns
elif grep -qE "\b(PASS|FAIL)\b" "$TEST_OUTPUT_FILE"; then
    passed_count=$(grep -cE "\bPASS\b" "$TEST_OUTPUT_FILE" || echo 0)
    failed_count=$(grep -cE "\bFAIL\b" "$TEST_OUTPUT_FILE" || echo 0)
    total_count=$((passed_count + failed_count))
    
    if [[ $total_count -gt 0 ]]; then
        pass_rate=$(python3 -c "print(f'{100.0 * $passed_count / $total_count:.2f}')")
        echo "TOTAL=$total_count PASSED=$passed_count FAILED=$failed_count RATE=${pass_rate}%"
    else
        log_error "No test results found in output"
        exit 2
    fi

# Strategy C: pytest success indicators
elif grep -q "=.*passed.*=" "$TEST_OUTPUT_FILE"; then
    # Extract from pytest summary line like "= 25 passed in 2.34s ="
    summary_line=$(grep "=.*passed.*=" "$TEST_OUTPUT_FILE" | tail -1)
    passed_count=$(echo "$summary_line" | sed -n 's/.*= \([0-9]\+\) passed.*/\1/p')
    failed_count=$(echo "$summary_line" | sed -n 's/.*= \([0-9]\+\) passed, \([0-9]\+\) failed.*/\2/p')
    
    if [[ -z "$failed_count" ]]; then
        failed_count=0
    fi
    
    total_count=$((passed_count + failed_count))
    
    if [[ $total_count -gt 0 ]]; then
        pass_rate=$(python3 -c "print(f'{100.0 * $passed_count / $total_count:.2f}')")
        echo "TOTAL=$total_count PASSED=$passed_count FAILED=$failed_count RATE=${pass_rate}%"
    else
        log_error "Could not parse test results"
        exit 2
    fi
else
    log_error "Could not determine test results from output"
    log_error "Please check the test output in: $TEST_OUTPUT_FILE"
    exit 2
fi

# Validate pass rate
pass_rate_num=$(echo "$pass_rate" | sed 's/%//')
if (( $(echo "$pass_rate_num >= $MIN_PASS_RATE" | bc -l 2>/dev/null || python3 -c "print(int($pass_rate_num >= $MIN_PASS_RATE))") )); then
    log_success "Test pass rate: ${pass_rate}% (≥ ${MIN_PASS_RATE}% required) ✓"
else
    log_error "Test pass rate: ${pass_rate}% (< ${MIN_PASS_RATE}% required) ✗"
    log_error "Not enough tests are passing to meet the 90% requirement"
    exit 1
fi

# Check coverage if available
if grep -q "TOTAL.*%" "$TEST_OUTPUT_FILE"; then
    coverage_line=$(grep "TOTAL.*%" "$TEST_OUTPUT_FILE" | tail -1)
    log_info "Coverage: $coverage_line"
fi

# Final validation
log_info "Validation Summary:"
log_info "  ✓ Execution time: ${elapsed_time}s (≤ ${MAX_TEST_TIME}s)"
log_info "  ✓ Pass rate: ${pass_rate}% (≥ ${MIN_PASS_RATE}%)"

if [[ $test_exit_code -eq 0 ]]; then
    log_success "All tests passed and requirements met!"
    echo ""
    log_info "Test output saved to: $TEST_OUTPUT_FILE"
    exit 0
else
    log_error "Some tests failed (exit code: $test_exit_code)"
    exit $test_exit_code
fi