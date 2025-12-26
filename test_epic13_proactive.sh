#!/bin/bash

# Epic 13: Proactive AI - Comprehensive Test Suite
# Tests all components of the proactive AI system using curl

# Don't use set -e - we want to continue even if individual tests fail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
AGENTIC_MEMORIES_URL="${AGENTIC_MEMORIES_URL:-http://localhost:8080}"
BACKEND_URL="${BACKEND_URL:-http://localhost:8001}"
TEST_USER_ID="test_user_epic13_$(date +%s)"
TIMESTAMP=$(date +%s)

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0

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

# Check if services are running
check_services() {
    print_test "Checking Service Availability"
    
    # Check agentic-memories (with curl timeout)
    if curl -s -f --max-time 5 "${AGENTIC_MEMORIES_URL}/health" > /dev/null 2>&1; then
        print_success "agentic-memories is running"
        AGENTIC_AVAILABLE=1
    else
        print_error "agentic-memories is not accessible at ${AGENTIC_MEMORIES_URL}"
        print_info "Some tests will be skipped. Start agentic-memories service to run all tests."
        AGENTIC_AVAILABLE=0
    fi
    
    # Check backend (with curl timeout)
    print_info "Checking backend at ${BACKEND_URL}..."
    BACKEND_RESPONSE=$(curl -s --max-time 2 "${BACKEND_URL}/health" 2>&1) || true
    if [ $? -eq 0 ] && echo "$BACKEND_RESPONSE" | grep -q "ok"; then
        print_success "Backend API is running"
        BACKEND_AVAILABLE=1
    else
        print_error "Backend API is not accessible at ${BACKEND_URL}"
        print_info "Some tests will be skipped. Start backend service to run all tests."
        BACKEND_AVAILABLE=0
    fi
    
    if [ "$AGENTIC_AVAILABLE" -eq 0 ] && [ "$BACKEND_AVAILABLE" -eq 0 ]; then
        print_error "Neither service is available. Cannot run tests."
        exit 1
    fi
    
    print_info "Service check complete. AGENTIC_AVAILABLE=${AGENTIC_AVAILABLE}, BACKEND_AVAILABLE=${BACKEND_AVAILABLE}"
}

# Test 1: Create Scheduled Trigger (CRUD)
test_create_scheduled_trigger() {
    if [ "$AGENTIC_AVAILABLE" -eq 0 ]; then
        print_info "Skipping test (agentic-memories not available)"
        return 0
    fi
    
    print_test "Test 1: Create Scheduled Trigger (CRUD)"
    
    # Create a scheduled trigger that fires every minute (for testing)
    TRIGGER_DATA=$(cat <<EOF
{
    "user_id": "${TEST_USER_ID}",
    "intent_name": "Daily Portfolio Update",
    "description": "Test scheduled trigger for Epic 13",
    "trigger_type": "cron",
    "trigger_schedule": {
        "cron_expression": "* * * * *",
        "timezone": "America/Los_Angeles"
    },
    "action_type": "notify",
    "action_context": "{\"user_context\":{\"name\":\"Test User\",\"preferences\":{\"tone\":\"friendly\",\"length\":\"brief\"}},\"execution_instructions\":{\"purpose\":\"Provide a daily portfolio update\",\"skip_conditions\":[],\"required_tools\":[\"get_portfolio\"]},\"message_guidance\":{\"tone\":\"friendly and concise\",\"length\":\"2-3 sentences\",\"include\":[\"total value\",\"top gainer\"],\"exclude\":[\"detailed breakdown\"]}}",
    "action_priority": "normal",
    "enabled": true,
    "metadata": {
        "test": true,
        "epic": "13",
        "timestamp": "${TIMESTAMP}"
    }
}
EOF
)
    
    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
        "${AGENTIC_MEMORIES_URL}/v1/intents" \
        -H "Content-Type: application/json" \
        -d "${TRIGGER_DATA}")
    
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    BODY=$(echo "$RESPONSE" | sed '$d')
    
    if [ "$HTTP_CODE" -eq 200 ] || [ "$HTTP_CODE" -eq 201 ]; then
        TRIGGER_ID=$(echo "$BODY" | jq -r '.id' 2>/dev/null || echo "$BODY" | grep -o '"id":"[^"]*' | head -1 | cut -d'"' -f4)
        print_success "Scheduled trigger created (ID: ${TRIGGER_ID})"
        echo "$TRIGGER_ID" > /tmp/epic13_scheduled_trigger_id.txt
        echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
    else
        print_error "Failed to create scheduled trigger (HTTP $HTTP_CODE)"
        echo "$BODY"
        return 1
    fi
}

# Test 2: Create Condition Trigger (Price Alert)
test_create_condition_trigger() {
    if [ "$AGENTIC_AVAILABLE" -eq 0 ]; then
        print_info "Skipping test (agentic-memories not available)"
        return 0
    fi
    
    print_test "Test 2: Create Condition Trigger (Price Alert)"
    
    TRIGGER_DATA=$(cat <<EOF
{
    "user_id": "${TEST_USER_ID}",
    "intent_name": "NVDA Price Alert",
    "description": "Alert when NVDA drops below $130",
    "trigger_type": "price",
    "trigger_condition": {
        "expression": "NVDA < 130",
        "cooldown_hours": 1,
        "fire_mode": "recurring"
    },
    "action_type": "notify",
    "action_context": "{\"user_context\":{\"name\":\"Test User\",\"preferences\":{\"tone\":\"alert\",\"length\":\"brief\"}},\"execution_instructions\":{\"purpose\":\"Alert user when NVDA price drops below threshold\",\"skip_conditions\":[],\"required_tools\":[]},\"message_guidance\":{\"tone\":\"alert and informative\",\"length\":\"1-2 sentences\",\"include\":[\"current price\",\"threshold\"],\"exclude\":[]}}",
    "action_priority": "high",
    "enabled": true,
    "metadata": {
        "test": true,
        "epic": "13",
        "timestamp": "${TIMESTAMP}"
    }
}
EOF
)
    
    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
        "${AGENTIC_MEMORIES_URL}/v1/intents" \
        -H "Content-Type: application/json" \
        -d "${TRIGGER_DATA}")
    
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    BODY=$(echo "$RESPONSE" | sed '$d')
    
    if [ "$HTTP_CODE" -eq 200 ] || [ "$HTTP_CODE" -eq 201 ]; then
        TRIGGER_ID=$(echo "$BODY" | jq -r '.id' 2>/dev/null || echo "$BODY" | grep -o '"id":"[^"]*' | head -1 | cut -d'"' -f4)
        print_success "Condition trigger created (ID: ${TRIGGER_ID})"
        echo "$TRIGGER_ID" > /tmp/epic13_condition_trigger_id.txt
        echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
    else
        print_error "Failed to create condition trigger (HTTP $HTTP_CODE)"
        echo "$BODY"
        return 1
    fi
}

# Test 3: List Intents
test_list_intents() {
    if [ "$AGENTIC_AVAILABLE" -eq 0 ]; then
        print_info "Skipping test (agentic-memories not available)"
        return 0
    fi
    
    print_test "Test 3: List Intents"
    
    RESPONSE=$(curl -s -w "\n%{http_code}" -X GET \
        "${AGENTIC_MEMORIES_URL}/v1/intents?user_id=${TEST_USER_ID}")
    
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    BODY=$(echo "$RESPONSE" | sed '$d')
    
    if [ "$HTTP_CODE" -eq 200 ]; then
        COUNT=$(echo "$BODY" | jq '. | length' 2>/dev/null || echo "0")
        print_success "Listed ${COUNT} intents for user"
        echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
    else
        print_error "Failed to list intents (HTTP $HTTP_CODE)"
        echo "$BODY"
        return 1
    fi
}

# Test 4: Get Intent
test_get_intent() {
    print_test "Test 4: Get Intent Details"
    
    # Try to get trigger ID from either scheduled or condition trigger
    if [ -f /tmp/epic13_scheduled_trigger_id.txt ]; then
        TRIGGER_ID=$(cat /tmp/epic13_scheduled_trigger_id.txt)
    elif [ -f /tmp/epic13_condition_trigger_id.txt ]; then
        TRIGGER_ID=$(cat /tmp/epic13_condition_trigger_id.txt)
    else
        print_error "No trigger ID found (run test 1 or 2 first)"
        return 1
    fi
    
    RESPONSE=$(curl -s -w "\n%{http_code}" -X GET \
        "${AGENTIC_MEMORIES_URL}/v1/intents/${TRIGGER_ID}")
    
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    BODY=$(echo "$RESPONSE" | sed '$d')
    
    if [ "$HTTP_CODE" -eq 200 ]; then
        INTENT_NAME=$(echo "$BODY" | jq -r '.intent_name' 2>/dev/null || echo "N/A")
        print_success "Retrieved intent: ${INTENT_NAME}"
        echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
    else
        print_error "Failed to get intent (HTTP $HTTP_CODE)"
        echo "$BODY"
        return 1
    fi
}

# Test 5: Update Intent
test_update_intent() {
    print_test "Test 5: Update Intent"
    
    # Try to get trigger ID from either scheduled or condition trigger
    if [ -f /tmp/epic13_scheduled_trigger_id.txt ]; then
        TRIGGER_ID=$(cat /tmp/epic13_scheduled_trigger_id.txt)
    elif [ -f /tmp/epic13_condition_trigger_id.txt ]; then
        TRIGGER_ID=$(cat /tmp/epic13_condition_trigger_id.txt)
    else
        print_error "No trigger ID found (run test 1 or 2 first)"
        return 1
    fi
    
    UPDATE_DATA=$(cat <<EOF
{
    "intent_name": "Updated Daily Portfolio Update",
    "action_priority": "high"
}
EOF
)
    
    RESPONSE=$(curl -s -w "\n%{http_code}" -X PUT \
        "${AGENTIC_MEMORIES_URL}/v1/intents/${TRIGGER_ID}" \
        -H "Content-Type: application/json" \
        -d "${UPDATE_DATA}")
    
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    BODY=$(echo "$RESPONSE" | sed '$d')
    
    if [ "$HTTP_CODE" -eq 200 ]; then
        INTENT_NAME=$(echo "$BODY" | jq -r '.intent_name' 2>/dev/null || echo "N/A")
        print_success "Updated intent: ${INTENT_NAME}"
        echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
    else
        print_error "Failed to update intent (HTTP $HTTP_CODE)"
        echo "$BODY"
        return 1
    fi
}

# Test 6: Get Pending Intents
test_get_pending() {
    print_test "Test 6: Get Pending Intents (Worker Polling)"
    
    RESPONSE=$(curl -s -w "\n%{http_code}" -X GET \
        "${AGENTIC_MEMORIES_URL}/v1/intents/pending?user_id=${TEST_USER_ID}")
    
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    BODY=$(echo "$RESPONSE" | sed '$d')
    
    if [ "$HTTP_CODE" -eq 200 ]; then
        COUNT=$(echo "$BODY" | jq '. | length' 2>/dev/null || echo "0")
        print_success "Found ${COUNT} pending intents"
        if [ "$COUNT" -gt 0 ]; then
            echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
        fi
    else
        print_error "Failed to get pending intents (HTTP $HTTP_CODE)"
        echo "$BODY"
        return 1
    fi
}

# Test 7: Claim Intent
test_claim_intent() {
    print_test "Test 7: Claim Intent (Worker Operation)"
    
    # Try to get trigger ID from either scheduled or condition trigger
    if [ -f /tmp/epic13_scheduled_trigger_id.txt ]; then
        TRIGGER_ID=$(cat /tmp/epic13_scheduled_trigger_id.txt)
    elif [ -f /tmp/epic13_condition_trigger_id.txt ]; then
        TRIGGER_ID=$(cat /tmp/epic13_condition_trigger_id.txt)
    else
        print_error "No trigger ID found (run test 1 or 2 first)"
        return 1
    fi
    
    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
        "${AGENTIC_MEMORIES_URL}/v1/intents/${TRIGGER_ID}/claim" \
        -H "Content-Type: application/json" \
        -d "{}")
    
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    BODY=$(echo "$RESPONSE" | sed '$d')
    
    if [ "$HTTP_CODE" -eq 200 ]; then
        CLAIMED_AT=$(echo "$BODY" | jq -r '.claimed_at' 2>/dev/null || echo "N/A")
        print_success "Intent claimed at: ${CLAIMED_AT}"
        echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
    elif [ "$HTTP_CODE" -eq 409 ]; then
        print_info "Intent already claimed (409 Conflict - expected for multi-worker safety)"
        echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
    else
        print_error "Failed to claim intent (HTTP $HTTP_CODE)"
        echo "$BODY"
        return 1
    fi
}

# Test 8: Fire Intent (Report Execution)
test_fire_intent() {
    print_test "Test 8: Fire Intent (Report Execution)"
    
    # Try to get trigger ID from either scheduled or condition trigger
    if [ -f /tmp/epic13_scheduled_trigger_id.txt ]; then
        TRIGGER_ID=$(cat /tmp/epic13_scheduled_trigger_id.txt)
    elif [ -f /tmp/epic13_condition_trigger_id.txt ]; then
        TRIGGER_ID=$(cat /tmp/epic13_condition_trigger_id.txt)
    else
        print_error "No trigger ID found (run test 1 or 2 first)"
        return 1
    fi
    
    FIRE_REPORT=$(cat <<EOF
{
    "status": "success",
    "message_id": "test_msg_${TIMESTAMP}",
    "message_preview": "Test proactive message",
    "evaluation_ms": 50,
    "generation_ms": 1200,
    "delivery_ms": 200,
    "tools_called": ["get_portfolio"],
    "skip_reason": null
}
EOF
)
    
    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
        "${AGENTIC_MEMORIES_URL}/v1/intents/${TRIGGER_ID}/fire" \
        -H "Content-Type: application/json" \
        -d "${FIRE_REPORT}")
    
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    BODY=$(echo "$RESPONSE" | sed '$d')
    
    if [ "$HTTP_CODE" -eq 200 ]; then
        COOLDOWN=$(echo "$BODY" | jq -r '.cooldown_active' 2>/dev/null || echo "N/A")
        print_success "Intent fired successfully (cooldown_active: ${COOLDOWN})"
        echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
    else
        print_error "Failed to fire intent (HTTP $HTTP_CODE)"
        echo "$BODY"
        return 1
    fi
}

# Test 9: Get Intent History
test_get_history() {
    print_test "Test 9: Get Intent Execution History"
    
    # Try to get trigger ID from either scheduled or condition trigger
    if [ -f /tmp/epic13_scheduled_trigger_id.txt ]; then
        TRIGGER_ID=$(cat /tmp/epic13_scheduled_trigger_id.txt)
    elif [ -f /tmp/epic13_condition_trigger_id.txt ]; then
        TRIGGER_ID=$(cat /tmp/epic13_condition_trigger_id.txt)
    else
        print_error "No trigger ID found (run test 1 or 2 first)"
        return 1
    fi
    
    RESPONSE=$(curl -s -w "\n%{http_code}" -X GET \
        "${AGENTIC_MEMORIES_URL}/v1/intents/${TRIGGER_ID}/history?limit=10&offset=0")
    
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    BODY=$(echo "$RESPONSE" | sed '$d')
    
    if [ "$HTTP_CODE" -eq 200 ]; then
        COUNT=$(echo "$BODY" | jq '. | length' 2>/dev/null || echo "0")
        print_success "Retrieved ${COUNT} history records"
        if [ "$COUNT" -gt 0 ]; then
            echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
        fi
    else
        print_error "Failed to get intent history (HTTP $HTTP_CODE)"
        echo "$BODY"
        return 1
    fi
}

# Test 10: Create Trigger via Chat (MCP Tools)
test_create_trigger_via_chat() {
    if [ "$BACKEND_AVAILABLE" -eq 0 ]; then
        print_info "Skipping test (backend not available)"
        return 0
    fi
    
    print_test "Test 10: Create Trigger via Chat Endpoint (MCP Tools)"
    
    CHAT_REQUEST=$(cat <<EOF
{
    "user_id": "${TEST_USER_ID}",
    "platform": "telegram",
    "message": "Remind me every morning at 8am to check my portfolio",
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
        CONVERSATION_ID=$(echo "$BODY" | jq -r '.conversation_id' 2>/dev/null || echo "N/A")
        STREAM_URL=$(echo "$BODY" | jq -r '.stream_url' 2>/dev/null || echo "N/A")
        print_success "Chat request accepted (conversation_id: ${CONVERSATION_ID})"
        print_info "Stream URL: ${STREAM_URL}"
        echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
    else
        print_error "Failed to create chat request (HTTP $HTTP_CODE)"
        echo "$BODY"
        return 1
    fi
}

# Test 11: Condition Evaluator Test (Price)
test_condition_evaluator_price() {
    print_test "Test 11: Condition Evaluator - Price (via Backend)"
    
    # This test would require a backend endpoint to test evaluators directly
    # For now, we'll test by creating a price trigger and checking if it evaluates
    print_info "Price evaluator is tested indirectly through condition triggers"
    print_info "Create a price trigger and let the worker evaluate it"
}

# Test 12: Subconscious Gate Test
test_subconscious_gate() {
    print_test "Test 12: Subconscious Gate (via Backend)"
    
    # This test would require a backend endpoint to test gate directly
    # For now, we'll test by creating triggers and observing gate behavior
    print_info "Subconscious gate is tested indirectly through trigger execution"
    print_info "Gate checks: recent contact, daily limit, quiet hours, opt-out"
}

# Test 13: Full End-to-End Flow
test_full_flow() {
    print_test "Test 13: Full End-to-End Flow"
    
    print_info "Creating a one-time trigger that fires in 2 minutes..."
    
    # Calculate next check time (2 minutes from now)
    NEXT_CHECK=$(date -u -v+2M +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u -d "+2 minutes" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ")")
    
    TRIGGER_DATA=$(cat <<EOF
{
    "user_id": "${TEST_USER_ID}",
    "intent_name": "E2E Test Trigger",
    "description": "End-to-end test trigger for Epic 13",
    "trigger_type": "once",
    "trigger_schedule": {
        "trigger_at": "${NEXT_CHECK}",
        "timezone": "UTC"
    },
    "action_type": "notify",
    "action_context": "{\"user_context\":{\"name\":\"Test User\"},\"execution_instructions\":{\"purpose\":\"Test end-to-end flow\",\"skip_conditions\":[],\"required_tools\":[]},\"message_guidance\":{\"tone\":\"test\",\"length\":\"brief\",\"include\":[],\"exclude\":[]}}",
    "action_priority": "normal",
    "enabled": true,
    "metadata": {
        "test": true,
        "epic": "13",
        "e2e": true
    }
}
EOF
)
    
    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
        "${AGENTIC_MEMORIES_URL}/v1/intents" \
        -H "Content-Type: application/json" \
        -d "${TRIGGER_DATA}")
    
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    BODY=$(echo "$RESPONSE" | sed '$d')
    
    if [ "$HTTP_CODE" -eq 200 ] || [ "$HTTP_CODE" -eq 201 ]; then
        TRIGGER_ID=$(echo "$BODY" | jq -r '.id' 2>/dev/null || echo "$BODY" | grep -o '"id":"[^"]*' | head -1 | cut -d'"' -f4)
        NEXT_CHECK_TIME=$(echo "$BODY" | jq -r '.next_check' 2>/dev/null || echo "N/A")
        print_success "E2E trigger created (ID: ${TRIGGER_ID})"
        print_info "Next check: ${NEXT_CHECK_TIME}"
        echo "$TRIGGER_ID" > /tmp/epic13_e2e_trigger_id.txt
        echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
        
        print_info "Waiting 10 seconds, then checking if trigger becomes pending..."
        sleep 10
        
        # Check if it's pending
        RESPONSE2=$(curl -s -w "\n%{http_code}" -X GET \
            "${AGENTIC_MEMORIES_URL}/v1/intents/pending?user_id=${TEST_USER_ID}")
        
        HTTP_CODE2=$(echo "$RESPONSE2" | tail -n1)
        BODY2=$(echo "$RESPONSE2" | sed '$d')
        
        if [ "$HTTP_CODE2" -eq 200 ]; then
            PENDING_COUNT=$(echo "$BODY2" | jq "[.[] | select(.id == \"${TRIGGER_ID}\")] | length" 2>/dev/null || echo "0")
            if [ "$PENDING_COUNT" -gt 0 ]; then
                print_success "Trigger is pending (ready for worker processing)"
            else
                print_info "Trigger not yet pending (may need more time or worker to process)"
            fi
        fi
    else
        print_error "Failed to create E2E trigger (HTTP $HTTP_CODE)"
        echo "$BODY"
        return 1
    fi
}

# Test 14: Delete Intent
test_delete_intent() {
    print_test "Test 14: Delete Intent (Cleanup)"
    
    if [ ! -f /tmp/epic13_scheduled_trigger_id.txt ]; then
        print_error "No trigger ID found (run test 1 first)"
        return 1
    fi
    
    TRIGGER_ID=$(cat /tmp/epic13_scheduled_trigger_id.txt)
    
    RESPONSE=$(curl -s -w "\n%{http_code}" -X DELETE \
        "${AGENTIC_MEMORIES_URL}/v1/intents/${TRIGGER_ID}")
    
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    BODY=$(echo "$RESPONSE" | sed '$d')
    
    if [ "$HTTP_CODE" -eq 200 ]; then
        print_success "Intent deleted successfully"
        echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
    else
        print_error "Failed to delete intent (HTTP $HTTP_CODE)"
        echo "$BODY"
        return 1
    fi
}

# Test 15: Error Handling
test_error_handling() {
    print_test "Test 15: Error Handling"
    
    # Test invalid trigger creation
    INVALID_DATA='{"user_id": "test", "invalid": "data"}'
    
    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
        "${AGENTIC_MEMORIES_URL}/v1/intents" \
        -H "Content-Type: application/json" \
        -d "${INVALID_DATA}")
    
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    
    if [ "$HTTP_CODE" -ge 400 ]; then
        print_success "Error handling works (returned HTTP ${HTTP_CODE} for invalid data)"
    else
        print_error "Error handling failed (expected 4xx, got ${HTTP_CODE})"
        return 1
    fi
    
    # Test getting non-existent intent
    RESPONSE2=$(curl -s -w "\n%{http_code}" -X GET \
        "${AGENTIC_MEMORIES_URL}/v1/intents/nonexistent_id_12345")
    
    HTTP_CODE2=$(echo "$RESPONSE2" | tail -n1)
    
    if [ "$HTTP_CODE2" -eq 404 ]; then
        print_success "404 returned for non-existent intent"
    else
        print_info "Non-existent intent returned HTTP ${HTTP_CODE2} (may be expected)"
    fi
}

# Main test execution
main() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════════════════════╗"
    echo "║                    Epic 13: Proactive AI - Test Suite                       ║"
    echo "╚══════════════════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    
    echo -e "${YELLOW}Configuration:${NC}"
    echo "  AGENTIC_MEMORIES_URL: ${AGENTIC_MEMORIES_URL}"
    echo "  BACKEND_URL: ${BACKEND_URL}"
    echo "  TEST_USER_ID: ${TEST_USER_ID}"
    echo ""
    
    # Initialize availability flags
    AGENTIC_AVAILABLE=0
    BACKEND_AVAILABLE=0
    
    # Run tests
    check_services
    
    # Only run agentic-memories tests if service is available
    if [ "$AGENTIC_AVAILABLE" -eq 1 ]; then
        test_create_scheduled_trigger || true
        test_create_condition_trigger || true
        test_list_intents || true
        test_get_intent || true
        test_update_intent || true
        test_get_pending || true
        test_claim_intent || true
        test_fire_intent || true
        test_get_history || true
        test_full_flow || true
        test_error_handling || true
        # Note: Delete test is last for cleanup, but we'll keep the trigger for inspection
        # test_delete_intent
    else
        print_info "Skipping agentic-memories tests (service not available)"
    fi
    
    # Only run backend tests if service is available
    if [ "$BACKEND_AVAILABLE" -eq 1 ]; then
        test_create_trigger_via_chat || true
    else
        print_info "Skipping backend tests (service not available)"
    fi
    
    # These are informational tests
    test_condition_evaluator_price || true
    test_subconscious_gate || true
    
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
        echo -e "${RED}✗ Some tests failed. Please review the output above.${NC}"
        exit 1
    fi
}

# Run main function
main

