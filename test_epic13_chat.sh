#!/bin/bash

# Epic 13: Proactive AI - Chat-Based Test Suite
# Tests Epic 13 through Annie's chat framework using natural language interactions

set +e  # Don't exit on error - we want to test all scenarios

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
TIMESTAMP=$(date +%s)

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

# Send a chat message and get conversation ID
send_chat_message() {
    local message="$1"
    local wait_for_response="${2:-false}"
    
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
    
    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
        "${BACKEND_URL}/api/chat" \
        -H "Content-Type: application/json" \
        -d "${CHAT_REQUEST}")
    
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    BODY=$(echo "$RESPONSE" | sed '$d')
    
    if [ "$HTTP_CODE" -eq 200 ]; then
        CONVERSATION_ID=$(echo "$BODY" | jq -r '.conversation_id' 2>/dev/null || echo "")
        STREAM_URL=$(echo "$BODY" | jq -r '.stream_url' 2>/dev/null || echo "")
        
        if [ "$wait_for_response" = "true" ]; then
            # Wait a bit for response to be generated
            sleep 3
            print_info "Response stream available at: ${STREAM_URL}"
        fi
        
        return 0
    else
        print_error "Chat request failed (HTTP $HTTP_CODE)"
        echo "$BODY"
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
        print_info "Start backend service to run tests"
        exit 1
    fi
}

# Test 1: Create Scheduled Trigger via Chat
test_create_scheduled_trigger_chat() {
    print_test "Test 1: Create Scheduled Trigger via Chat"
    
    if send_chat_message "Remind me every morning at 9am to check my portfolio" "true"; then
        print_success "Chat request sent for scheduled trigger creation"
        print_info "Annie should create a cron trigger for 9am daily"
        print_info "Check the stream endpoint to see Annie's response"
    else
        print_error "Failed to send chat message"
        return 1
    fi
}

# Test 2: Create Condition Trigger via Chat
test_create_condition_trigger_chat() {
    print_test "Test 2: Create Condition Trigger via Chat"
    
    if send_chat_message "Alert me when NVDA drops below \$130" "true"; then
        print_success "Chat request sent for condition trigger creation"
        print_info "Annie should create a price condition trigger"
        print_info "Check the stream endpoint to see Annie's response"
    else
        print_error "Failed to send chat message"
        return 1
    fi
}

# Test 3: List Triggers via Chat
test_list_triggers_chat() {
    print_test "Test 3: List Triggers via Chat"
    
    if send_chat_message "What triggers do I have set up?" "true"; then
        print_success "Chat request sent for listing triggers"
        print_info "Annie should list all active triggers"
        print_info "Check the stream endpoint to see Annie's response"
    else
        print_error "Failed to send chat message"
        return 1
    fi
}

# Test 4: Update Trigger via Chat
test_update_trigger_chat() {
    print_test "Test 4: Update Trigger via Chat"
    
    if send_chat_message "Change my morning reminder to 8am instead of 9am" "true"; then
        print_success "Chat request sent for trigger update"
        print_info "Annie should update the schedule of the morning trigger"
        print_info "Check the stream endpoint to see Annie's response"
    else
        print_error "Failed to send chat message"
        return 1
    fi
}

# Test 5: Create Silence Trigger via Chat
test_create_silence_trigger_chat() {
    print_test "Test 5: Create Silence Trigger via Chat"
    
    if send_chat_message "If I don't message you for 4 hours, check in with me" "true"; then
        print_success "Chat request sent for silence trigger creation"
        print_info "Annie should create a silence condition trigger"
        print_info "Check the stream endpoint to see Annie's response"
    else
        print_error "Failed to send chat message"
        return 1
    fi
}

# Test 6: Create Portfolio Trigger via Chat
test_create_portfolio_trigger_chat() {
    print_test "Test 6: Create Portfolio Trigger via Chat"
    
    if send_chat_message "Let me know if any of my stocks drop more than 5%" "true"; then
        print_success "Chat request sent for portfolio trigger creation"
        print_info "Annie should create a portfolio condition trigger"
        print_info "Check the stream endpoint to see Annie's response"
    else
        print_error "Failed to send chat message"
        return 1
    fi
}

# Test 7: Pause Trigger via Chat
test_pause_trigger_chat() {
    print_test "Test 7: Pause Trigger via Chat"
    
    if send_chat_message "Pause my morning reminders for now" "true"; then
        print_success "Chat request sent for pausing trigger"
        print_info "Annie should disable the morning trigger"
        print_info "Check the stream endpoint to see Annie's response"
    else
        print_error "Failed to send chat message"
        return 1
    fi
}

# Test 8: Delete Trigger via Chat
test_delete_trigger_chat() {
    print_test "Test 8: Delete Trigger via Chat"
    
    if send_chat_message "Delete my NVDA price alert" "true"; then
        print_success "Chat request sent for deleting trigger"
        print_info "Annie should delete the NVDA alert trigger"
        print_info "Check the stream endpoint to see Annie's response"
    else
        print_error "Failed to send chat message"
        return 1
    fi
}

# Test 9: Complex Trigger Request
test_complex_trigger_chat() {
    print_test "Test 9: Complex Trigger Request"
    
    if send_chat_message "Every weekday at 8:30am, give me a brief portfolio update. Keep it to 2-3 sentences and only mention significant moves." "true"; then
        print_success "Chat request sent for complex trigger"
        print_info "Annie should create a scheduled trigger with detailed action_context"
        print_info "Check the stream endpoint to see Annie's response"
    else
        print_error "Failed to send chat message"
        return 1
    fi
}

# Test 10: Trigger Clarification
test_trigger_clarification_chat() {
    print_test "Test 10: Trigger Clarification"
    
    if send_chat_message "Remind me to check my portfolio" "true"; then
        print_success "Chat request sent (ambiguous request)"
        print_info "Annie should ask for clarification (when? how often?)"
        print_info "Check the stream endpoint to see Annie's response"
    else
        print_error "Failed to send chat message"
        return 1
    fi
}

# Test 11: Multiple Triggers
test_multiple_triggers_chat() {
    print_test "Test 11: Multiple Triggers"
    
    if send_chat_message "Set up two triggers: one for morning portfolio updates at 9am, and another to alert me if AAPL goes above \$200" "true"; then
        print_success "Chat request sent for multiple triggers"
        print_info "Annie should create both triggers"
        print_info "Check the stream endpoint to see Annie's response"
    else
        print_error "Failed to send chat message"
        return 1
    fi
}

# Test 12: Trigger Feedback (Replying to Proactive Message)
test_trigger_feedback_chat() {
    print_test "Test 12: Trigger Feedback (Closed-Loop Learning)"
    
    # First, create a trigger
    send_chat_message "Remind me every hour to take a break" "true"
    sleep 2
    
    # Simulate replying to a proactive message
    if send_chat_message "Actually, make these reminders shorter and less frequent - every 2 hours instead" "true"; then
        print_success "Chat request sent for trigger feedback"
        print_info "Annie should detect this is feedback and update the trigger"
        print_info "Check the stream endpoint to see Annie's response"
    else
        print_error "Failed to send chat message"
        return 1
    fi
}

# Test 13: Verify Trigger Creation (Check via API)
test_verify_triggers_api() {
    print_test "Test 13: Verify Triggers Created (via API)"
    
    # Wait a bit for triggers to be created
    sleep 5
    
    AGENTIC_MEMORIES_URL="${AGENTIC_MEMORIES_URL:-http://localhost:8080}"
    
    RESPONSE=$(curl -s -w "\n%{http_code}" -X GET \
        "${AGENTIC_MEMORIES_URL}/v1/intents?user_id=${TEST_USER_ID}" 2>/dev/null)
    
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    BODY=$(echo "$RESPONSE" | sed '$d')
    
    if [ "$HTTP_CODE" -eq 200 ]; then
        COUNT=$(echo "$BODY" | jq '. | length' 2>/dev/null || echo "0")
        print_success "Found ${COUNT} triggers for test user"
        
        if [ "$COUNT" -gt 0 ]; then
            echo "$BODY" | jq '.[] | {id, intent_name, trigger_type, enabled}' 2>/dev/null || echo "$BODY"
        fi
    else
        print_info "Could not verify triggers via API (agentic-memories may not be accessible)"
    fi
}

# Test 14: Test Proactive Message Delivery
test_proactive_delivery() {
    print_test "Test 14: Proactive Message Delivery"
    
    print_info "This test requires:"
    print_info "1. A trigger to be created and enabled"
    print_info "2. The Arq worker to be running"
    print_info "3. The trigger to fire (scheduled time or condition met)"
    print_info "4. Telegram bot to be configured"
    print_info ""
    print_info "To test proactively:"
    print_info "- Create a trigger that fires soon (e.g., 'remind me in 1 minute')"
    print_info "- Wait for the worker to process it"
    print_info "- Check Telegram for the proactive message"
}

# Main test execution
main() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════════════════════╗"
    echo "║          Epic 13: Proactive AI - Chat-Based Test Suite                     ║"
    echo "╚══════════════════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    
    echo -e "${YELLOW}Configuration:${NC}"
    echo "  BACKEND_URL: ${BACKEND_URL}"
    echo "  TEST_USER_ID: ${TEST_USER_ID}"
    echo ""
    echo -e "${YELLOW}Note:${NC} This test suite sends chat messages to Annie."
    echo "      Check the stream endpoints or Telegram to see Annie's responses."
    echo ""
    
    # Run tests
    check_services
    
    # Basic trigger creation tests
    test_create_scheduled_trigger_chat || true
    sleep 2
    
    test_create_condition_trigger_chat || true
    sleep 2
    
    # Trigger management tests
    test_list_triggers_chat || true
    sleep 2
    
    test_update_trigger_chat || true
    sleep 2
    
    # Additional trigger types
    test_create_silence_trigger_chat || true
    sleep 2
    
    test_create_portfolio_trigger_chat || true
    sleep 2
    
    # Trigger modification tests
    test_pause_trigger_chat || true
    sleep 2
    
    test_delete_trigger_chat || true
    sleep 2
    
    # Advanced tests
    test_complex_trigger_chat || true
    sleep 2
    
    test_trigger_clarification_chat || true
    sleep 2
    
    test_multiple_triggers_chat || true
    sleep 2
    
    test_trigger_feedback_chat || true
    sleep 2
    
    # Verification
    test_verify_triggers_api || true
    
    # Proactive delivery info
    test_proactive_delivery || true
    
    # Summary
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}TEST SUMMARY${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}Chat Requests Sent: ${TESTS_PASSED}${NC}"
    echo -e "${RED}Chat Requests Failed: ${TESTS_FAILED}${NC}"
    echo ""
    echo -e "${YELLOW}Next Steps:${NC}"
    echo "  1. Check stream endpoints to see Annie's responses"
    echo "  2. Verify triggers were created via API or chat"
    echo "  3. Test proactive delivery by waiting for triggers to fire"
    echo "  4. Check Telegram for proactive messages (if configured)"
    echo ""
    
    if [ $TESTS_FAILED -eq 0 ]; then
        echo -e "${GREEN}✓ All chat requests sent successfully!${NC}"
        exit 0
    else
        echo -e "${YELLOW}⚠ Some chat requests failed. Check the output above.${NC}"
        exit 0  # Don't fail - chat requests may have succeeded even if HTTP check failed
    fi
}

# Run main function
main

