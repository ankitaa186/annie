#!/bin/bash
set -e

USER_ID="e2e_fixed_api_$(date +%s)"
BACKEND_URL="http://localhost:8001"

echo "=========================================="
echo "E2E TEST: Updated agentic-memories Integration"
echo "=========================================="
echo "User ID: $USER_ID"
echo ""

# Send conversation
echo "--- Sending conversation with farewell ---"
RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/chat" \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"platform\": \"telegram\",
    \"message\": \"Thanks!\"
  }")

CONV_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['conversation_id'])" 2>/dev/null || echo "")
echo "Conversation ID: $CONV_ID"
echo ""

# Wait for background memory storage
echo "Waiting 10 seconds for memory storage..."
sleep 10

# Check backend logs
echo ""
echo "--- Backend Logs (Memory Storage) ---"
docker compose logs backend --tail 30 | grep -E "memory|Memory" | tail -15

echo ""
echo "✅ TEST COMPLETE"
