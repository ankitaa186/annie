#!/bin/bash
set -e

USER_ID="test_api_user_$(date +%s)"

echo "=========================================="
echo "Testing CORRECT agentic-memories API"
echo "=========================================="
echo "User ID: $USER_ID"
echo ""

# Build the request payload
REQUEST_PAYLOAD=$(cat <<PAYLOAD
{
  "user_id": "$USER_ID",
  "history": [
    {"role": "user", "content": "I want to invest \$10,000. What should I do?"},
    {"role": "assistant", "content": "Based on your investment goal, I'd recommend considering index funds like VTSAX or VTI for long-term growth."},
    {"role": "user", "content": "I prefer moderate risk, focusing on long-term growth"},
    {"role": "assistant", "content": "Great choice! Moderate risk with index funds aligns well with long-term growth. VTSAX and VTI are excellent options."},
    {"role": "user", "content": "OK, I'll invest in index funds. I'll buy VTSAX and VTI."}
  ],
  "metadata": {
    "platform": "telegram",
    "conversation_id": "conv_test_123"
  }
}
PAYLOAD
)

echo "REQUEST PAYLOAD:"
echo "$REQUEST_PAYLOAD" | python3 -m json.tool
echo ""
echo "=========================================="
echo "Sending POST request to /v1/store"
echo "=========================================="

RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "http://localhost:8080/v1/store" \
  -H "Content-Type: application/json" \
  -d "$REQUEST_PAYLOAD")

HTTP_BODY=$(echo "$RESPONSE" | sed -e 's/HTTP_STATUS\:.*//g')
HTTP_STATUS=$(echo "$RESPONSE" | tr -d '\n' | sed -e 's/.*HTTP_STATUS://')

echo ""
echo "RESPONSE STATUS: $HTTP_STATUS"
echo "RESPONSE BODY:"
echo "$HTTP_BODY" | python3 -m json.tool 2>/dev/null || echo "$HTTP_BODY"
echo ""

if [ "$HTTP_STATUS" = "200" ]; then
    echo "✅ SUCCESS: Memory stored successfully!"
    echo ""
    echo "=========================================="
    echo "Retrieving stored memory"
    echo "=========================================="
    curl -s "http://localhost:8080/v1/retrieve?user_id=$USER_ID&limit=5" | python3 -m json.tool
else
    echo "❌ FAILED: Memory storage failed with status $HTTP_STATUS"
fi

echo ""
echo "=========================================="
echo "TEST COMPLETE"
echo "=========================================="
