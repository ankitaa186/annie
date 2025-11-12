# API Specifications

## Overview

This document provides detailed API specifications for Annie's Backend API, including endpoints, request/response formats, authentication, and error handling.

## Base URL

**Development**: `http://localhost:8000`  
**Production**: `https://api.annie.yourdomain.com`

## API Versioning

**Current Version**: v1  
**Format**: `/api/v1/{endpoint}`

## Authentication

### V1 (Internal Services)
- No authentication required
- Services communicate within Docker network

### Future (Production)
- API key authentication
- JWT tokens for user sessions
- Rate limiting per API key

## Core Endpoints

### Health Check

#### GET /health

**Purpose**: Basic health check for load balancer

**Response**:
```json
{
  "status": "ok",
  "timestamp": "2025-11-10T00:00:00Z"
}
```

#### GET /health/detailed

**Purpose**: Detailed health check for monitoring

**Response**:
```json
{
  "status": "ok",
  "timestamp": "2025-11-10T00:00:00Z",
  "checks": {
    "mcp_server": true,
    "redis": true,
    "llm_api": true,
    "agentic_memories": true
  },
  "version": "1.0.0",
  "uptime_seconds": 3600
}
```

**Status Codes**:
- `200 OK` - All checks passed
- `503 Service Unavailable` - One or more checks failed

### Chat Endpoints

#### POST /api/v1/chat

**Purpose**: Send a chat message and get a response

**Request**:
```json
{
  "user_id": "user_123",
  "platform": "telegram",
  "message": "What's the weather like today?",
  "conversation_id": "conv_abc",
  "context": {
    "session_id": "session_xyz",
    "metadata": {}
  }
}
```

**Response**:
```json
{
  "conversation_id": "conv_abc",
  "response": "I'll check the weather for you...",
  "stream_url": "/api/v1/stream/conv_abc",
  "tools_used": ["internet_search"],
  "memories_retrieved": 3,
  "tokens_used": {
    "input": 150,
    "output": 300
  }
}
```

**Status Codes**:
- `200 OK` - Message processed successfully
- `400 Bad Request` - Invalid request format
- `429 Too Many Requests` - Rate limit exceeded
- `500 Internal Server Error` - Server error

#### GET /api/v1/stream/{conversation_id}

**Purpose**: Stream LLM response via Server-Sent Events

**Headers**:
```
Accept: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
```

**Response** (SSE Format):
```
data: {"type":"token","content":"Hello"}

data: {"type":"token","content":" there"}

data: {"type":"tool_call","tool":"internet_search","arguments":{"query":"weather"}}

data: {"type":"tool_result","tool":"internet_search","result":{...}}

data: {"type":"token","content":"It's sunny"}

data: {"type":"done","tokens_used":{"input":150,"output":300}}

```

**Event Types**:
- `token` - Text token from LLM
- `tool_call` - LLM requested tool execution
- `tool_result` - Tool execution result
- `done` - Stream complete
- `error` - Error occurred

### Conversation Management

#### GET /api/v1/conversations/{user_id}

**Purpose**: Get conversation history for a user

**Query Parameters**:
- `limit` (default: 10) - Number of conversations to return
- `offset` (default: 0) - Pagination offset
- `platform` (optional) - Filter by platform

**Response**:
```json
{
  "user_id": "user_123",
  "conversations": [
    {
      "conversation_id": "conv_abc",
      "platform": "telegram",
      "started_at": "2025-11-10T00:00:00Z",
      "last_activity": "2025-11-10T00:05:00Z",
      "message_count": 15,
      "preview": "What's the weather like..."
    }
  ],
  "total": 50,
  "has_more": true
}
```

#### GET /api/v1/conversations/{conversation_id}/messages

**Purpose**: Get messages for a specific conversation

**Query Parameters**:
- `limit` (default: 50) - Number of messages to return
- `offset` (default: 0) - Pagination offset

**Response**:
```json
{
  "conversation_id": "conv_abc",
  "messages": [
    {
      "message_id": "msg_1",
      "role": "user",
      "content": "Hello!",
      "timestamp": "2025-11-10T00:00:00Z"
    },
    {
      "message_id": "msg_2",
      "role": "assistant",
      "content": "Hi there!",
      "timestamp": "2025-11-10T00:00:01Z",
      "tools_used": [],
      "memories_retrieved": 0
    }
  ],
  "total": 15,
  "has_more": false
}
```

### User State

#### GET /api/v1/users/{user_id}/state

**Purpose**: Get user state (affection score, preferences, etc.)

**Response**:
```json
{
  "user_id": "user_123",
  "affection_score": 45.5,
  "preferences": {
    "language": "en",
    "timezone": "UTC"
  },
  "stats": {
    "total_conversations": 50,
    "total_messages": 500,
    "active_since": "2025-01-01T00:00:00Z"
  }
}
```

#### PATCH /api/v1/users/{user_id}/state

**Purpose**: Update user state

**Request**:
```json
{
  "affection_score": 50.0,
  "preferences": {
    "language": "en"
  }
}
```

**Response**:
```json
{
  "user_id": "user_123",
  "updated_fields": ["affection_score", "preferences"],
  "success": true
}
```

## MCP Tool Endpoints (Internal)

### List Tools

#### GET /api/v1/mcp/tools

**Purpose**: List available MCP tools

**Response**:
```json
{
  "tools": [
    {
      "name": "internet_search",
      "description": "Search the internet for current information",
      "input_schema": {
        "type": "object",
        "properties": {
          "query": {"type": "string"}
        },
        "required": ["query"]
      }
    },
    {
      "name": "store_memory",
      "description": "Store conversation as memories",
      "input_schema": {
        "type": "object",
        "properties": {
          "user_id": {"type": "string"},
          "history": {"type": "array"}
        },
        "required": ["user_id", "history"]
      }
    }
  ]
}
```

### Call Tool

#### POST /api/v1/mcp/tools/{tool_name}

**Purpose**: Execute an MCP tool

**Request**:
```json
{
  "arguments": {
    "query": "Python programming"
  }
}
```

**Response**:
```json
{
  "tool": "internet_search",
  "success": true,
  "result": {
    "results": [
      {
        "title": "Python.org",
        "url": "https://python.org",
        "snippet": "Official Python website..."
      }
    ]
  },
  "execution_time_ms": 250
}
```

## Error Responses

### Standard Error Format

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "Missing required field: user_id",
    "details": {
      "field": "user_id",
      "expected": "string"
    }
  },
  "timestamp": "2025-11-10T00:00:00Z",
  "request_id": "req_123"
}
```

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `INVALID_REQUEST` | 400 | Request format invalid |
| `MISSING_FIELD` | 400 | Required field missing |
| `INVALID_FIELD` | 400 | Field value invalid |
| `UNAUTHORIZED` | 401 | Authentication required |
| `FORBIDDEN` | 403 | Insufficient permissions |
| `NOT_FOUND` | 404 | Resource not found |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |
| `LLM_ERROR` | 500 | LLM API error |
| `MCP_ERROR` | 500 | MCP tool execution error |
| `DATABASE_ERROR` | 500 | Database error |
| `INTERNAL_ERROR` | 500 | Internal server error |

## Rate Limiting

### V1 (Basic)
- No rate limiting
- Client-side throttling recommended

### Future (Production)
- **Per User**: 60 requests/minute
- **Per IP**: 100 requests/minute
- **Burst**: 10 requests/second

**Rate Limit Headers**:
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1699564800
```

## Request/Response Headers

### Common Request Headers

```
Content-Type: application/json
Accept: application/json
User-Agent: AnnieTelegramBot/1.0
```

### Common Response Headers

```
Content-Type: application/json
X-Request-ID: req_123abc
X-Response-Time: 250ms
```

## WebSocket API (Future)

### Connection

**Endpoint**: `ws://localhost:8000/ws`

**Upgrade Request**:
```
GET /ws HTTP/1.1
Host: localhost:8000
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
```

### Message Format

**Client → Server**:
```json
{
  "type": "message",
  "user_id": "user_123",
  "message": "Hello!",
  "conversation_id": "conv_abc"
}
```

**Server → Client**:
```json
{
  "type": "token",
  "conversation_id": "conv_abc",
  "content": "Hi there!"
}
```

## API Client Examples

### Python

```python
import httpx
import asyncio

async def chat(user_id: str, message: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/v1/chat",
            json={
                "user_id": user_id,
                "platform": "api",
                "message": message
            },
            timeout=30.0
        )
        return response.json()

# Usage
result = asyncio.run(chat("user_123", "Hello!"))
print(result["response"])
```

### cURL

```bash
# Send chat message
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "platform": "api",
    "message": "Hello!"
  }'

# Stream response
curl -N http://localhost:8000/api/v1/stream/conv_abc \
  -H "Accept: text/event-stream"

# Health check
curl http://localhost:8000/health
```

### JavaScript

```javascript
// Send chat message
async function chat(userId, message) {
  const response = await fetch('http://localhost:8000/api/v1/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      user_id: userId,
      platform: 'web',
      message: message
    })
  });
  return await response.json();
}

// Stream response
async function streamResponse(conversationId) {
  const eventSource = new EventSource(
    `http://localhost:8000/api/v1/stream/${conversationId}`
  );
  
  eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log(data);
    
    if (data.type === 'done') {
      eventSource.close();
    }
  };
}
```

## Testing the API

### Using Postman

Import the provided Postman collection:
```
/Users/Ankit/dev/annie/docs/03-technical/Annie_API.postman_collection.json
```

### Using pytest

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_chat_endpoint():
    async with AsyncClient(base_url="http://localhost:8000") as client:
        response = await client.post(
            "/api/v1/chat",
            json={
                "user_id": "test_user",
                "platform": "test",
                "message": "Hello!"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert "conversation_id" in data
```

## API Changelog

### v1.0 (Current)
- Initial release
- Basic chat endpoints
- SSE streaming
- Health checks
- MCP tool integration

### Future Versions
- v1.1: WebSocket support
- v1.2: Voice endpoints
- v2.0: A2A protocol integration

## References

- FastAPI Documentation: https://fastapi.tiangolo.com
- SSE Specification: https://html.spec.whatwg.org/multipage/server-sent-events.html
- OpenAPI Specification: https://swagger.io/specification/

