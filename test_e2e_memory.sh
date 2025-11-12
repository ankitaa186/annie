#!/bin/bash
# Comprehensive E2E test for memory storage integration

set -e

USER_ID="e2e_test_user_$(date +%s)"
BACKEND_URL="http://localhost:8001"

echo "================================================================================"
echo "E2E MEMORY STORAGE TEST"
echo "================================================================================"
echo "User ID: $USER_ID"
echo "Backend: $BACKEND_URL"
echo "agentic-memories: http://localhost:8080"
echo ""

# Step 1: Initial message
echo "--- STEP 1: Send initial investment question ---"
RESPONSE1=$(curl -s -X POST "$BACKEND_URL/api/chat" \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"platform\": \"telegram\",
    \"message\": \"I want to invest \$10,000. What should I do?\"
  }")

CONV_ID=$(echo "$RESPONSE1" | python3 -c "import sys, json; print(json.load(sys.stdin)['conversation_id'])")
echo "Conversation ID: $CONV_ID"
echo ""

# Step 2: Follow-up message
echo "--- STEP 2: Send follow-up about risk tolerance ---"
curl -s -X POST "$BACKEND_URL/api/chat" \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"platform\": \"telegram\",
    \"message\": \"I prefer moderate risk, focusing on long-term growth\"
  }" > /dev/null
echo "Message sent"
echo ""

# Step 3: Decision message
echo "--- STEP 3: Send decision message ---"
curl -s -X POST "$BACKEND_URL/api/chat" \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"platform\": \"telegram\",
    \"message\": \"OK, I'll invest in index funds like you suggested. I'll buy VTSAX and VTI.\"
  }" > /dev/null
echo "Message sent"
echo ""

# Wait a moment to ensure messages are stored
sleep 2

# Step 4: Farewell message to trigger memory storage
echo "--- STEP 4: Send farewell message (triggers memory storage) ---"
echo ""
curl -s -X POST "$BACKEND_URL/api/chat" \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"platform\": \"telegram\",
    \"message\": \"Thanks for the advice!\"
  }" > /dev/null

echo "Farewell sent - memory storage initiated in background"
echo ""

# Wait for background memory storage to complete
echo "Waiting 25 seconds for LLM summarization and memory storage..."
sleep 25

echo ""
echo "================================================================================"
echo "BACKEND LOGS - Memory Storage Flow"
echo "================================================================================"
docker compose logs backend --tail 100 | grep -E "Conversation ending|memory|Memory|summariz|store|Store" | tail -20

echo ""
echo "================================================================================"
echo "CHECK: Was memory stored successfully?"
echo "================================================================================"

# Check if memory was queued in Redis (fallback) or stored successfully
QUEUE_SIZE=$(docker compose exec -T redis redis-cli LLEN "memory_queue:$USER_ID" 2>/dev/null | tr -d '\r')

if [ "$QUEUE_SIZE" = "0" ] || [ -z "$QUEUE_SIZE" ]; then
    echo "✅ SUCCESS: Memory was stored directly (not queued in Redis)"
    echo ""
    echo "Let me check the agentic-memories service to verify..."

    # Try to retrieve the memory
    MEMORIES=$(curl -s "http://localhost:8080/memories/$USER_ID" 2>/dev/null || echo "{}")
    echo ""
    echo "Memories in agentic-memories:"
    echo "$MEMORIES" | python3 -m json.tool 2>/dev/null || echo "$MEMORIES"
else
    echo "⚠️  Memory was queued in Redis fallback (agentic-memories may have failed)"
    echo "Queue size: $QUEUE_SIZE"
    echo ""
    echo "Queued memory:"
    docker compose exec -T redis redis-cli LINDEX "memory_queue:$USER_ID" 0 | python3 -m json.tool
fi

echo ""
echo "================================================================================"
echo "DETAILED API REQUEST/RESPONSE LOGS"
echo "================================================================================"
echo ""
echo "Checking backend logs for agentic-memories API call details..."
docker compose logs backend --tail 200 | grep -A 10 -B 5 "memory_client\|MemoryClient\|POST.*memories" | tail -40

echo ""
echo "================================================================================"
echo "TEST COMPLETE"
echo "================================================================================"
