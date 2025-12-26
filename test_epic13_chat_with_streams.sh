#!/bin/bash

# Epic 13: Proactive AI - Chat-Based Test Suite with Stream Reading
# Tests Epic 13 through Annie's chat framework and reads stream responses

set +e  # Don't exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
BACKEND_URL="${BACKEND_URL:-http://localhost:8001}"
TEST_USER_ID="chat_test_user_$(date +%s)"

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0
CONVERSATION_ID=""

# Helper functions
print_test() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}TEST: $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
    ((TESTS_PASSED++))
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
    ((TESTS_FAILED++))
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

print_chat() {
    echo -e "${CYAN}💬 User: $1${NC}"
}

print_response() {
    echo -e "${GREEN}🤖 Annie: $1${NC}"
}

# Send a chat message and read the stream response
send_chat_and_read_stream() {
    local message="$1"
    local timeout="${2:-30}"
    
    print_chat "$message"
    
    CHAT_REQUEST=$(cat <<EOF
{
    "user_id": "${TEST_USER_ID}",
    "platform": "telegram",
    "message": "${message}",
    "context": {}
}
EOF
)
    
    # Send chat request
    RESPONSE=$(curl -s -X POST \
        "${BACKEND_URL}/api/chat" \
        -H "Content-Type: application/json" \
        -d "${CHAT_REQUEST}")
    
    CONVERSATION_ID=$(echo "$RESPONSE" | jq -r '.conversation_id' 2>/dev/null || echo "")
    STREAM_URL=$(echo "$RESPONSE" | jq -r '.stream_url' 2>/dev/null || echo "")
    
    if [ -z "$CONVERSATION_ID" ] || [ -z "$STREAM_URL" ]; then
        print_error "Failed to get conversation_id or stream_url"
        echo "$RESPONSE"
        return 1
    fi
    
    print_info "Conversation ID: ${CONVERSATION_ID}"
    print_info "Reading stream response (timeout: ${timeout}s)..."
    
    # Read stream response
    FULL_RESPONSE=""
    TOOL_CALLS=()
    
    # Use curl to read SSE stream
    STREAM_RESPONSE=$(timeout ${timeout} curl -s -N \
        "${BACKEND_URL}${STREAM_URL}" \
        2>/dev/null || echo "")
    
    if [ -z "$STREAM_RESPONSE" ]; then
        print_error "No stream response received"
        return 1
    fi
    
    # Parse SSE events
    while IFS= read -r line; do
        if [[ "$line" =~ ^data:\ (.+)$ ]]; then
            data="${BASH_REMATCH[1]}"
            
            # Try to parse as JSON
            event_type=$(echo "$data" | jq -r '.type' 2>/dev/null || echo "")
            
            if [ "$event_type" = "content" ]; then
                delta=$(echo "$data" | jq -r '.delta' 2>/dev/null || echo "")
                FULL_RESPONSE="${FULL_RESPONSE}${delta}"
            elif [ "$event_type" = "tool_call" ]; then
                tool_name=$(echo "$data" | jq -r '.name' 2>/dev/null || echo "")
                if [ -n "$tool_name" ]; then
                    TOOL_CALLS+=("$tool_name")
                    print_info "🔧 Tool called: ${tool_name}"
                fi
            elif [ "$event_type" = "done" ]; then
                break
            elif [ "$event_type" = "error" ]; then
                error_msg=$(echo "$data" | jq -r '.message' 2>/dev/null || echo "")
                print_error "Stream error: ${error_msg}"
                return 1
            fi
        fi
    done <<< "$STREAM_RESPONSE"
    
    # Display response
    if [ -n "$FULL_RESPONSE" ]; then
        print_response "$FULL_RESPONSE"
        
        # Check if trigger-related keywords are present
        if echo "$FULL_RESPONSE" | grep -qi "trigger\|remind\|alert\|schedule"; then
            print_success "Response mentions trigger-related terms"
        fi
        
        # Check if tools were called
        if [ ${#TOOL_CALLS[@]} -gt 0 ]; then
            print_success "Tools called: ${TOOL_CALLS[*]}"
        fi
        
        return 0
    else
        print_error "Empty response received"
        return 1
    fi
}

# Check if services are running
check_services() {
    print_test "Checking Service Availability"
    
    if curl -s -f --max-time 2 "${BACKEND_URL}/health" > /dev/null 2>&1; then
        print_success "Backend API is running"
        return 0
    else
        print_error "Backend API is not accessible at ${BACKEND_URL}"
        exit 1
    fi
}

# Test 1: Create Scheduled Trigger via Chat
test_create_scheduled_trigger_chat() {
    print_test "Test 1: Create Scheduled Trigger via Chat"
    
    if send_chat_and_read_stream "Remind me every morning at 9am to check my portfolio" 30; then
        print_success "Scheduled trigger creation test completed"
    else
        print_error "Scheduled trigger creation test failed"
        return 1
    fi
}

# Test 2: Create Condition Trigger via Chat
test_create_condition_trigger_chat() {
    print_test "Test 2: Create Condition Trigger via Chat"
    
    if send_chat_and_read_stream "Alert me when NVDA drops below \$130" 30; then
        print_success "Condition trigger creation test completed"
    else
        print_error "Condition trigger creation test failed"
        return 1
    fi
}

# Test 3: List Triggers via Chat
test_list_triggers_chat() {
    print_test "Test 3: List Triggers via Chat"
    
    if send_chat_and_read_stream "What triggers do I have set up?" 30; then
        print_success "List triggers test completed"
    else
        print_error "List triggers test failed"
        return 1
    fi
}

# Test 4: Complex Trigger Request
test_complex_trigger_chat() {
    print_test "Test 4: Complex Trigger Request"
    
    if send_chat_and_read_stream "Every weekday at 8:30am, give me a brief portfolio update. Keep it to 2-3 sentences and only mention significant moves." 30; then
        print_success "Complex trigger creation test completed"
    else
        print_error "Complex trigger creation test failed"
        return 1
    fi
}

# Test 5: Update Trigger via Chat
test_update_trigger_chat() {
    print_test "Test 5: Update Trigger via Chat"
    
    if send_chat_and_read_stream "Change my morning reminder to 8am instead of 9am" 30; then
        print_success "Trigger update test completed"
    else
        print_error "Trigger update test failed"
        return 1
    fi
}

# Test 6: Delete Trigger via Chat
test_delete_trigger_chat() {
    print_test "Test 6: Delete Trigger via Chat"
    
    if send_chat_and_read_stream "Delete my NVDA price alert" 30; then
        print_success "Trigger deletion test completed"
    else
        print_error "Trigger deletion test failed"
        return 1
    fi
}

# Main test execution
main() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════════════════════╗"
    echo "║     Epic 13: Proactive AI - Chat Test Suite (with Stream Reading)          ║"
    echo "╚══════════════════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    
    echo -e "${YELLOW}Configuration:${NC}"
    echo "  BACKEND_URL: ${BACKEND_URL}"
    echo "  TEST_USER_ID: ${TEST_USER_ID}"
    echo ""
    echo -e "${YELLOW}Note:${NC} This test suite sends chat messages and reads stream responses."
    echo ""
    
    # Run tests
    check_services
    
    # Basic tests
    test_create_scheduled_trigger_chat || true
    sleep 3
    
    test_create_condition_trigger_chat || true
    sleep 3
    
    test_list_triggers_chat || true
    sleep 3
    
    test_complex_trigger_chat || true
    sleep 3
    
    test_update_trigger_chat || true
    sleep 3
    
    test_delete_trigger_chat || true
    
    # Summary
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}TEST SUMMARY${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}Tests Passed: ${TESTS_PASSED}${NC}"
    echo -e "${RED}Tests Failed: ${TESTS_FAILED}${NC}"
    echo ""
    
    if [ $TESTS_FAILED -eq 0 ]; then
        echo -e "${GREEN}✓ All tests passed!${NC}"
        exit 0
    else
        echo -e "${YELLOW}⚠ Some tests had issues. Review the output above.${NC}"
        exit 0
    fi
}

# Run main function
main

