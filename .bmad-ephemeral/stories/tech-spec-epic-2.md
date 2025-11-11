# Epic Technical Specification: Core Chat & LLM Integration

Date: 2025-11-11
Author: Ankit
Epic ID: epic-2
Status: Draft

---

## Overview

Epic 2 implements the core backend API with LLM integration, enabling Annie to provide intelligent, streaming responses powered by Grok-4 (primary) and ChatGPT-5 (fallback). This epic establishes the foundation for AI-powered decision support by integrating advanced LLM capabilities, real-time streaming, function calling for tool invocation, conversation state management via Redis, and robust error handling patterns.

The epic builds upon Epic 1's infrastructure foundation to deliver the core chat functionality that enables Annie to assist users with 80% of day-to-day decisions. It implements the backend API endpoints, LLM client with provider fallback, Server-Sent Events (SSE) streaming for real-time responses, function calling integration with MCP tools, Redis-based state management, and comprehensive error handling to ensure graceful degradation.

## Objectives and Scope

**In Scope:**
- FastAPI backend with `/api/chat` and `/api/stream/{conversation_id}` endpoints
- Unified LLM client supporting Grok-4 (primary) and ChatGPT-5 (fallback) with automatic failover
- Server-Sent Events (SSE) streaming for real-time token delivery (<500ms first token p95)
- Function calling integration enabling LLM to invoke MCP tools (internet search, memories, stock analysis)
- Conversation state management with Redis (1-hour session TTL, last 20 messages or 4000 tokens)
- Error handling patterns for LLM failures, external service failures, rate limiting, timeouts, and validation errors
- Performance optimization to meet <2s p95 response time requirement
- Request/response logging and observability

**Out of Scope:**
- agentic-memories integration (Epic 3 - Memory & Persistence)
- MCP tool implementations for internet search, memories, stock analysis (Epic 4 - Decision Support Tools)
- Telegram bot interface implementation (Epic 5 - Telegram Bot Interface)
- End-to-end integration testing (Epic 6 - Integration & Quality)
- PostgreSQL persistent storage (deferred to V2.0)
- Web interface or 3D avatar (deferred to V1.1)
- Voice interaction or multi-modality (deferred to V1.2/V2.0)

**Success Criteria:**
- Backend API successfully processes chat requests and returns streaming responses
- LLM streaming delivers first token within 500ms (p95) and complete response within 2s (p95)
- Function calling successfully invokes MCP tools and incorporates results into LLM responses
- Redis conversation state persists across requests with <50ms retrieval time (p95)
- Error handling provides graceful degradation when external services fail
- All 6 stories (2.1-2.6) implemented with acceptance criteria met

## System Architecture Alignment

**Architecture Components:**

Epic 2 implements the **Backend API Service** and **LLM Client** components defined in the Architecture Plan (docs/02-architecture/ARCHITECTURE_PLAN.md).

**Backend API Service (FastAPI):**
- Implements endpoints: `POST /api/chat`, `GET /api/stream/{conversation_id}`, `GET /health`, `GET /api/conversations/{user_id}`
- Manages conversation state via Redis
- Orchestrates LLM API calls with streaming
- Coordinates MCP tool calls via Docker exec pattern (established in Epic 1)
- Handles SSE streaming for real-time response delivery

**LLM Client Component:**
- Unified client for Grok-4 (XAI API) and ChatGPT-5 (OpenAI API)
- Automatic provider failover (Grok-4 → ChatGPT-5 within 2 seconds)
- Function calling support for MCP tool invocation
- Streaming token delivery via SSE
- Rate limiting and error handling

**State Manager Component:**
- Redis-based session management (1-hour TTL)
- Conversation history caching (30-minute TTL)
- Real-time state synchronization across requests
- Eventual consistency pattern (PostgreSQL deferred to V2.0)

**Integration with Existing Architecture:**
- **Epic 1 Foundation**: Builds on Docker Compose orchestration, MCP server HTTP transport (port 8002), structured logging, environment configuration
- **Epic 3 Preparation**: Establishes conversation state structure for future memory integration
- **Epic 4 Preparation**: Implements function calling framework for future tool implementations
- **Epic 5 Preparation**: Provides `/api/chat` and `/api/stream` endpoints for Telegram bot integration

**Communication Patterns:**
- Telegram Bot → Backend API (HTTP)
- Backend API → MCP Server (HTTP on port 8002)
- Backend API → Redis (Redis protocol)
- Backend API → LLM APIs (HTTPS)
- Backend API → Telegram Bot (SSE streaming)

## Detailed Design

### Services and Modules

| Module | Responsibilities | Inputs | Outputs | Owner |
|--------|-----------------|--------|---------|-------|
| **LLM Client** (`backend/api/llm_client.py`) | - Authenticate with Grok-4 and ChatGPT-5<br>- Manage provider selection and failover<br>- Handle streaming responses<br>- Parse function calling requests<br>- Rate limiting and retry logic | - Chat messages<br>- Conversation context<br>- Provider config (API keys, base URLs)<br>- Streaming flag | - Streamed tokens (SSE)<br>- Function call requests<br>- Error messages<br>- Provider metadata | Story 2.2 |
| **Chat Endpoint Handler** (`backend/api/routes/chat.py`) | - Receive chat requests from Telegram bot<br>- Load conversation state from Redis<br>- Orchestrate LLM calls<br>- Coordinate MCP tool calls<br>- Return conversation ID | - User message<br>- User ID<br>- Platform identifier | - Conversation ID<br>- Initial response metadata<br>- Error responses | Story 2.1 |
| **Streaming Handler** (`backend/api/routes/stream.py`) | - Establish SSE connection<br>- Stream LLM tokens to client<br>- Handle client disconnections<br>- Send completion events<br>- Manage concurrent streams | - Conversation ID<br>- SSE connection | - Token events (SSE)<br>- Completion events<br>- Error events<br>- Connection status | Story 2.3 |
| **MCP Client** (`backend/api/mcp_client.py`) | - Format function call requests<br>- Call MCP server via HTTP (port 8002)<br>- Parse tool responses<br>- Handle tool errors | - Tool name<br>- Tool arguments<br>- Request context | - Tool results<br>- Error messages<br>- Execution metadata | Story 2.4 |
| **State Manager** (`backend/api/state.py`) | - Create/update sessions in Redis<br>- Store conversation history<br>- Retrieve conversation context<br>- Manage session TTL (1 hour)<br>- Handle Redis connection failures | - User ID<br>- Platform<br>- Messages<br>- Session data | - Session object<br>- Conversation history (last 20 messages or 4000 tokens)<br>- Cache status | Story 2.5 |
| **Error Handler** (`backend/api/errors.py`) | - Catch unhandled exceptions<br>- Format error responses<br>- Log errors with context<br>- Handle external service failures<br>- Manage timeouts and rate limits | - Exception object<br>- Request context | - User-friendly error response<br>- Structured error logs<br>- HTTP status codes | Story 2.6 |

### Data Models and Contracts

**Session Model** (Redis):
```python
{
    "user_id": str,              # Telegram user ID
    "platform": str,             # "telegram"
    "conversation_id": str,      # Unique conversation identifier
    "created_at": datetime,      # Session creation timestamp (ISO 8601)
    "last_activity": datetime,   # Last message timestamp (ISO 8601)
    "message_count": int,        # Total messages in session
    "ttl": int                   # Time to live in seconds (3600 = 1 hour)
}
```

**Conversation History Model** (Redis List):
```python
[
    {
        "role": str,             # "user" | "assistant" | "system" | "tool"
        "content": str,          # Message content
        "timestamp": datetime,   # Message timestamp (ISO 8601)
        "tool_calls": [          # Optional: function calls made
            {
                "tool": str,
                "arguments": dict,
                "result": dict
            }
        ]
    },
    # ... last 20 messages or 4000 tokens max
]
```

**LLM Request Model**:
```python
{
    "messages": [
        {
            "role": str,         # "user" | "assistant" | "system"
            "content": str
        }
    ],
    "stream": bool,              # True for streaming responses
    "temperature": float,        # 0.0-1.0 (default: 0.7)
    "max_tokens": int,           # Maximum tokens in response
    "functions": [               # Optional: available tools for function calling
        {
            "name": str,
            "description": str,
            "parameters": dict   # JSON Schema
        }
    ]
}
```

**LLM Response Model** (Streaming):
```python
# Token event
{
    "type": "token",
    "content": str,              # Partial response token
    "timestamp": datetime
}

# Completion event
{
    "type": "done",
    "tokens_used": {
        "prompt": int,
        "completion": int,
        "total": int
    },
    "finish_reason": str         # "stop" | "length" | "function_call"
}

# Error event
{
    "type": "error",
    "message": str,              # User-friendly error message
    "code": str,                 # Error code (e.g., "RATE_LIMIT")
    "request_id": str
}
```

**Function Call Model**:
```python
{
    "name": str,                 # Tool name (e.g., "internet_search")
    "arguments": dict,           # Tool-specific arguments
    "call_id": str               # Unique call identifier
}
```

**Error Response Model**:
```python
{
    "error": {
        "code": str,             # Error code (e.g., "INTERNAL_ERROR", "RATE_LIMIT")
        "message": str,          # User-friendly message
        "request_id": str,       # Request identifier for debugging
        "retry_after": int       # Optional: seconds to wait before retry
    }
}
```

### APIs and Interfaces

**Backend API Endpoints:**

1. **POST /api/chat**
   - **Description**: Process incoming chat message and initiate conversation
   - **Request**:
     ```json
     {
       "user_id": "123456",
       "platform": "telegram",
       "message": "What should I invest in?",
       "context": {}
     }
     ```
   - **Response** (200 OK):
     ```json
     {
       "conversation_id": "conv_abc123",
       "status": "streaming",
       "stream_url": "/api/stream/conv_abc123"
     }
     ```
   - **Error Responses**:
     - 400: Invalid input (validation error)
     - 429: Rate limit exceeded
     - 500: Internal server error
     - 503: Service unavailable (LLM/Redis down)

2. **GET /api/stream/{conversation_id}**
   - **Description**: Stream LLM response tokens via Server-Sent Events
   - **Headers**: `Accept: text/event-stream`
   - **Response** (SSE stream):
     ```
     data: {"type":"token","content":"I "}

     data: {"type":"token","content":"recommend "}

     data: {"type":"token","content":"diversifying"}

     data: {"type":"done","tokens_used":{"prompt":100,"completion":200}}
     ```
   - **Error Events**:
     ```
     data: {"type":"error","message":"LLM service unavailable","code":"LLM_ERROR"}
     ```

3. **GET /api/conversations/{user_id}**
   - **Description**: Retrieve conversation history for a user (paginated)
   - **Query Parameters**:
     - `page`: Page number (default: 1)
     - `limit`: Messages per page (default: 50, max: 50)
   - **Response** (200 OK):
     ```json
     {
       "user_id": "123456",
       "conversations": [
         {
           "conversation_id": "conv_abc123",
           "created_at": "2025-11-11T10:00:00Z",
           "message_count": 5,
           "last_activity": "2025-11-11T10:05:00Z"
         }
       ],
       "pagination": {
         "page": 1,
         "limit": 50,
         "total": 120
       }
     }
     ```

4. **GET /health**
   - **Description**: Basic health check
   - **Response** (200 OK):
     ```json
     {
       "status": "ok",
       "timestamp": "2025-11-11T10:00:00Z"
     }
     ```

5. **GET /health/detailed**
   - **Description**: Detailed component health status
   - **Response** (200 OK):
     ```json
     {
       "status": "ok",
       "components": {
         "mcp_server": "ok",
         "redis": "ok",
         "llm_api": "ok",
         "agentic_memories": "ok"
       },
       "timestamp": "2025-11-11T10:00:00Z"
     }
     ```

**LLM Provider APIs:**

1. **XAI API (Grok-4)**
   - **Endpoint**: `https://api.x.ai/v1/chat/completions`
   - **Authentication**: Bearer token (GROK_API_KEY)
   - **Streaming**: Supported via `stream=true`

2. **OpenAI API (ChatGPT-5)**
   - **Endpoint**: `https://api.openai.com/v1/chat/completions`
   - **Authentication**: Bearer token (CHATGPT_API_KEY)
   - **Streaming**: Supported via `stream=true`

**MCP Server Interface:**

- **HTTP Endpoint**: `http://mcp-server:8002/tools/call`
- **Method**: POST
- **Request Format**:
  ```json
  {
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "internet_search",
      "arguments": {"query": "stock market trends"}
    },
    "id": "call-1"
  }
  ```
- **Response Format**:
  ```json
  {
    "jsonrpc": "2.0",
    "result": {
      "status": "success",
      "data": {...}
    },
    "id": "call-1"
  }
  ```

### Workflows and Sequencing

**1. Standard Chat Flow (No Tools)**

```
1. User sends message via Telegram
2. Telegram Bot → POST /api/chat
   - Body: {user_id, platform, message}
3. Backend API:
   - Generate conversation_id
   - Load session from Redis (or create new)
   - Return {conversation_id, stream_url}
4. Telegram Bot → GET /api/stream/{conversation_id}
   - Establish SSE connection
5. Backend API:
   - Load conversation history from Redis (last 20 messages or 4000 tokens)
   - Construct LLM context
   - Call Grok-4 API with stream=true
6. Grok-4 API streams tokens
7. Backend API:
   - Forward tokens via SSE to Telegram Bot
   - Send events: {"type":"token","content":"..."}
8. LLM completes response
9. Backend API:
   - Send completion event: {"type":"done","tokens_used":{...}}
   - Save conversation to Redis (with 30-min TTL)
   - Update session last_activity
10. Telegram Bot displays complete response to user
```

**2. Chat Flow with Function Calling**

```
1-5. [Same as standard flow through LLM context construction]
6. Grok-4 API responds with function_call instead of content:
   {
     "function_call": {
       "name": "internet_search",
       "arguments": "{\"query\":\"stock market trends\"}"
     }
   }
7. Backend API detects function_call:
   - Parse function name and arguments
   - Call MCP Client
8. MCP Client:
   - Format JSON-RPC 2.0 request
   - HTTP POST to http://mcp-server:8002/tools/call
9. MCP Server:
   - Execute internet_search tool
   - Call Brave Search API
   - Return results
10. Backend API:
    - Receive tool results
    - Add to conversation context as "tool" role message
    - Call Grok-4 API again with tool results
11. Grok-4 generates final response incorporating tool results
12. Backend API streams response to Telegram Bot (same as step 7-9 in standard flow)
13. Complete and save conversation
```

**3. Provider Failover Flow**

```
1-5. [Same as standard flow]
6. Backend API calls Grok-4 API
7. Grok-4 API fails (timeout/error/rate limit)
8. Backend API LLM Client:
   - Detect failure (within 2 seconds)
   - Log error with details
   - Automatically switch to ChatGPT-5
9. Backend API calls ChatGPT-5 API with same context
10. ChatGPT-5 API streams tokens
11-13. [Continue as standard flow with ChatGPT-5]
```

**4. Error Handling Flow**

```
1-5. [Same as standard flow]
6. Backend API detects error (LLM failure, Redis down, timeout)
7. Error Handler:
   - Catch exception
   - Determine error type
   - Generate user-friendly message
8. Backend API sends error event via SSE:
   data: {"type":"error","message":"I'm experiencing technical difficulties...","code":"LLM_ERROR"}
9. Telegram Bot displays error message to user
10. Backend API logs error with full context (user_id, conversation_id, request_id)
```

**5. Session Management Flow**

```
1. New user sends first message
2. Backend API:
   - Check Redis for existing session (key: session:{user_id})
   - No session found
   - Create new session with TTL=3600 (1 hour)
3. Store session in Redis:
   - Key: session:{user_id}
   - Value: {user_id, platform, conversation_id, created_at, last_activity, message_count}
4. Store conversation history in Redis:
   - Key: conversation:{conversation_id}
   - Value: List of messages
   - TTL: 1800 (30 minutes)
5. User sends subsequent messages within 1 hour
6. Backend API:
   - Load session from Redis
   - Update last_activity
   - Reset TTL to 3600
7. User inactive for >1 hour
8. Redis automatically expires session
9. Next message creates new session
```

## Non-Functional Requirements

### Performance

**Latency Requirements** (from PRD Success Metrics):

| Metric | Target (p95) | Measurement Point | Story |
|--------|--------------|-------------------|-------|
| **First Token Latency** | <500ms | Time from request to first SSE token | Story 2.3 |
| **Total Response Time** | <2s | Time from request to completion event | Story 2.2, 2.3 |
| **API Response Time** | <500ms | Backend API endpoint response | Story 2.1 |
| **MCP Tool Execution** | <1s average | Tool call to result return | Story 2.4 |
| **Conversation Retrieval** | <50ms | Redis query for conversation history | Story 2.5 |
| **Session Creation** | <100ms | Create new session in Redis | Story 2.5 |
| **LLM Provider Failover** | <2s | Detect Grok-4 failure and switch to ChatGPT-5 | Story 2.2 |

**Throughput Requirements**:
- Concurrent SSE streams: Up to 100 simultaneous connections (Story 2.3 AC#7)
- Chat requests: 1000 requests/minute per instance
- Redis operations: 10,000 ops/second (within Redis capacity)

**Optimization Strategies**:
- Connection pooling for Redis and HTTP clients
- Lazy loading of conversation history (only last 20 messages or 4000 tokens)
- Streaming responses to reduce perceived latency
- Async I/O for all external API calls
- Response caching in Redis (30-minute TTL)

**Performance Monitoring**:
- Log all request durations with `duration_ms` field
- Track p50, p95, p99 latencies for each endpoint
- Monitor LLM API response times by provider
- Alert on >500ms first token latency or >2s total response time

### Security

**Authentication & Authorization**:
- Telegram Bot API authentication via `TELEGRAM_BOT_TOKEN`
- LLM provider authentication via API keys (`GROK_API_KEY`, `CHATGPT_API_KEY`)
- No user authentication in V1.0 (relying on Telegram's user authentication)
- MCP server communication over internal Docker network (no external exposure)

**API Key Management**:
- All API keys loaded from environment variables (never hardcoded)
- API keys masked in logs (show first 4 and last 4 characters only) - implemented in `backend/api/config.py`
- Sensitive values excluded from error messages and user-facing responses
- No API keys in version control (enforced via `.gitignore`)

**Data Protection**:
- Conversation data stored in Redis with TTL (auto-expiration after inactivity)
- No persistent storage of messages in V1.0 (PostgreSQL deferred to V2.0)
- HTTPS for all external API calls (LLM providers, MCP external services)
- Internal service communication over Docker network (isolated from host)

**Input Validation**:
- All API endpoints validate request payloads (Story 2.6 AC#5)
- User message length limits (max 4000 characters)
- Conversation history size limits (max 20 messages or 4000 tokens)
- Sanitize user inputs before passing to LLM to prevent prompt injection

**CORS Configuration**:
- Development: `allow_origins=["*"]` (Story 2.1)
- Production: Restrict to specific origins via `ALLOWED_ORIGINS` environment variable (Technical Debt item)

**Rate Limiting**:
- Handle LLM provider rate limits gracefully (Story 2.6 AC#4)
- Return 429 status code with `retry_after` header when rate limited
- Queue requests or implement exponential backoff for retries

**Threat Mitigation**:
- Prevent LLM prompt injection via input sanitization
- Protect against SSRF attacks in MCP tool calls (validate URLs in tools)
- Prevent DoS via connection limits (max 100 concurrent SSE streams)
- No sensitive data logged (API keys, user personal information)

### Reliability/Availability

**Uptime Target**: 99%+ uptime for decision-critical moments (from PRD Success Metrics)

**High Availability Strategies**:
- **LLM Provider Failover**: Automatic Grok-4 → ChatGPT-5 failover within 2 seconds (Story 2.2 AC#3)
- **Redis Failover**: Continue without conversation context if Redis unavailable (Story 2.5 AC#6, Story 2.6 AC#2)
- **MCP Server Failover**: Graceful degradation when MCP server unavailable (Story 2.6 AC#3)
- **Service Restart**: Docker restart policy `unless-stopped` for all services

**Error Handling & Graceful Degradation**:
- LLM failure: Switch to fallback provider or return user-friendly error (Story 2.2 AC#4)
- Redis failure: Continue without conversation context, log error (Story 2.5 AC#6)
- MCP tool failure: Inform user tool unavailable, continue chat without tool (Story 2.4 AC#6)
- Timeout handling: 30-second timeout for all requests (Story 2.6 AC#6)

**Recovery Mechanisms**:
- Retry logic with exponential backoff for transient failures
- Circuit breaker pattern for external service calls (LLM, MCP)
- Health checks for all services (`/health` and `/health/detailed` endpoints)
- Docker health checks with automatic container restart on failure

**Data Persistence & Loss Prevention**:
- Redis AOF (Append-Only File) for persistence across restarts
- Conversation TTL of 30 minutes (acceptable data loss window for V1.0)
- Session TTL of 1 hour (acceptable for temporary state)
- No critical data loss risk (persistent storage deferred to V2.0 PostgreSQL)

**Monitoring & Alerts**:
- Health check endpoints monitored every 30 seconds
- Alert on service degradation (Redis down, LLM provider down)
- Track error rate (target: <1% of requests from PRD)
- Log all failures with request context for debugging

### Observability

**Structured Logging**:
- All services use structured logging from Epic 1 (Story 1.4)
- Log format: `[timestamp] [level] [service] message [extra_fields]`
- Log levels: DEBUG (dev), INFO (prod), WARNING, ERROR, CRITICAL
- Sensitive data masked in logs (API keys, user IDs when appropriate)

**Request Logging** (Story 2.1 AC#6):
- Log all API requests with: method, path, status code, response time
- Include request_id for request tracing across services
- Log conversation_id and user_id for debugging
- Example: `GET /api/chat - 200 - 145ms [request_id=req_abc123, user_id=12345]`

**Error Logging** (Story 2.6 AC#7):
- All errors include request context: user_id, conversation_id, request_id
- Error messages include: error type, message, stack trace, timestamp
- External service failures logged separately: LLM provider, Redis, MCP server
- Example: `[ERROR] LLM provider failure [provider=grok-4, error=timeout, request_id=req_abc123]`

**Performance Metrics**:
- Log duration_ms for all requests and external API calls
- Track token usage for LLM calls (prompt tokens, completion tokens)
- Monitor Redis operation latency
- Track MCP tool execution time

**Tool Call Logging** (Story 2.4):
- Log all function calls: tool name, arguments, results, duration
- Example: `[INFO] Tool call completed [tool=internet_search, duration=850ms, status=success]`
- Include tool results summary (not full content to avoid log bloat)

**Streaming Logging** (Story 2.3):
- Log SSE connection establishment and closure
- Track concurrent connection count
- Log stream errors and disconnections
- Monitor token streaming rate (tokens/second)

**Provider Failover Logging** (Story 2.2):
- Log all provider switches: from provider, to provider, reason, duration
- Example: `[WARNING] Provider failover [from=grok-4, to=chatgpt-5, reason=timeout, duration=1.8s]`

**Metrics Collection**:
- Request count by endpoint and status code
- Error rate by error type and service
- LLM provider usage and success rate
- Redis hit/miss ratio for conversation cache
- SSE connection count and duration

**Tracing**:
- Request ID propagation across all services
- Conversation ID tracking for multi-request flows
- Correlation of tool calls with chat requests
- End-to-end tracing from Telegram message to response

## Dependencies and Integrations

### Python Dependencies

**Backend API** (`backend/requirements.txt`):
| Package | Version | Purpose | Story |
|---------|---------|---------|-------|
| `fastapi` | >=0.104.0 | Web framework for REST API | Story 2.1 |
| `uvicorn[standard]` | >=0.24.0 | ASGI server for FastAPI | Story 2.1 |
| `httpx` | >=0.25.0 | Async HTTP client for MCP server and LLM APIs | Story 2.2, 2.4 |
| `redis` | TBD | Redis client for state management | Story 2.5 |
| `sse-starlette` | TBD | Server-Sent Events support for FastAPI | Story 2.3 |
| `pydantic` | >=2.0 | Data validation and serialization (included with FastAPI) | All stories |
| `python-dotenv` | TBD | Environment variable loading (optional) | Story 2.1 |

**MCP Server** (`mcp_server/requirements.txt`):
| Package | Version | Purpose | Story |
|---------|---------|---------|-------|
| `mcp` | >=0.1.0 | MCP Python SDK | Epic 1 (Story 1.6) |
| `fastapi` | >=0.104.0 | HTTP server framework | Epic 1 (Story 1.6) |
| `uvicorn` | >=0.24.0 | ASGI server | Epic 1 (Story 1.6) |
| `requests` | >=2.31.0 | HTTP client for external APIs | Epic 1 (Story 1.6) |

**Telegram Bot** (`telegram_bot/requirements.txt`):
| Package | Version | Purpose | Story |
|---------|---------|---------|-------|
| `python-telegram-bot` | TBD | Telegram Bot API client | Epic 5 |
| `httpx` | TBD | HTTP client for backend API | Epic 5 |
| `sseclient-py` | TBD | SSE client for streaming responses | Epic 5 |

### External Service Integrations

**1. XAI API (Grok-4 Provider)**
- **Endpoint**: `https://api.x.ai/v1/chat/completions`
- **Authentication**: Bearer token via `GROK_API_KEY` environment variable
- **Purpose**: Primary LLM provider for chat completions and function calling
- **Integration Point**: `backend/api/llm_client.py` (Story 2.2)
- **Protocol**: HTTPS REST API (OpenAI-compatible)
- **Features Used**: Chat completions, streaming, function calling
- **Rate Limits**: TBD (handle gracefully per Story 2.6)
- **Failover**: Automatic failover to ChatGPT-5 on failure (Story 2.2 AC#3)

**2. OpenAI API (ChatGPT-5 Provider)**
- **Endpoint**: `https://api.openai.com/v1/chat/completions`
- **Authentication**: Bearer token via `CHATGPT_API_KEY` environment variable
- **Purpose**: Fallback LLM provider when Grok-4 unavailable
- **Integration Point**: `backend/api/llm_client.py` (Story 2.2)
- **Protocol**: HTTPS REST API
- **Features Used**: Chat completions, streaming, function calling
- **Rate Limits**: TBD (handle gracefully per Story 2.6)
- **Usage Pattern**: Only invoked on Grok-4 failure (within 2 seconds)

**3. Redis Service**
- **Endpoint**: `redis:6379` (internal Docker network)
- **Purpose**: Session state storage, conversation history caching, rate limiting
- **Integration Point**: `backend/api/state.py` (Story 2.5)
- **Protocol**: Redis protocol
- **Version**: Redis 7.2-alpine
- **Data Structures**: Strings (sessions), Lists (conversation history), Sets (active users)
- **Persistence**: AOF (Append-Only File) enabled
- **TTL Strategy**: Sessions (1 hour), Conversations (30 minutes)
- **Failover**: Continue without conversation context on failure (Story 2.5 AC#6)

**4. MCP Server (Internal Service)**
- **Endpoint**: `http://mcp-server:8002` (internal Docker network)
- **Purpose**: Tool execution (internet search, memories, stock analysis)
- **Integration Point**: `backend/api/mcp_client.py` (Epic 1, Story 2.4)
- **Protocol**: HTTP with JSON-RPC 2.0 over HTTP
- **Version**: Custom Python MCP SDK server
- **Tools Available**: `internet_search`, `store_memory`, `retrieve_memories`, `get_portfolio_summary` (Epic 4)
- **Transport**: HTTP (refactored from stdio in Epic 1)
- **Failover**: Graceful degradation on failure (Story 2.6 AC#3)

**5. agentic-memories Service (External)**
- **Endpoint**: Configured via `AGENTIC_MEMORIES_URL` environment variable (default: `http://host.docker.internal:8080`)
- **Purpose**: Persistent memory storage and retrieval (integrated in Epic 3)
- **Integration Point**: MCP Server tools (`store_memory`, `retrieve_memories`)
- **Protocol**: HTTP REST API
- **Usage Pattern**: Called via MCP tools when LLM requests memory operations
- **Failover**: Graceful degradation (Epic 3 implementation)
- **Note**: Integration deferred to Epic 3, placeholder health check in Epic 2

**6. Telegram Bot API (External)**
- **Endpoint**: `https://api.telegram.org/bot{token}/`
- **Authentication**: `TELEGRAM_BOT_TOKEN` environment variable
- **Purpose**: Telegram messaging platform integration
- **Integration Point**: `telegram_bot/bot.py` (Epic 5)
- **Protocol**: HTTPS REST API (long polling)
- **Usage Pattern**: Telegram Bot polls for updates, forwards to Backend API
- **Note**: Integration deferred to Epic 5, not part of Epic 2

### Internal Service Dependencies

**Epic 2 Dependencies on Epic 1:**
- **Docker Compose orchestration**: All services defined in `docker-compose.yml`
- **MCP Server HTTP transport**: Refactored to HTTP in Epic 1 (port 8002)
- **Structured logging**: Logging infrastructure from Story 1.4
- **Environment configuration**: Config validation from Story 1.3
- **Health check patterns**: Health check endpoints from Story 1.1
- **Operational scripts**: `make` commands and `scripts/run_docker.sh` from Story 1.5

**Epic 2 Prepares for Future Epics:**
- **Epic 3 (Memory & Persistence)**: Conversation state structure and function calling framework
- **Epic 4 (Decision Support Tools)**: MCP Client and function calling integration
- **Epic 5 (Telegram Bot Interface)**: `/api/chat` and `/api/stream` endpoints ready for bot integration
- **Epic 6 (Integration & Quality)**: Health checks, error handling, logging for end-to-end testing

### Infrastructure Dependencies

**Docker & Docker Compose**:
- **Docker Version**: 20.10+ required
- **Docker Compose**: v2 required
- **Purpose**: Service orchestration, networking, volume management
- **Networks**: `annie-network` (bridge network for inter-service communication)
- **Volumes**: `redis-data` (persistent Redis storage)

**Operating System**:
- **Supported**: macOS, Linux, Windows (with WSL2)
- **Python Version**: 3.12+ required for all services

**Development Tools**:
- **Make**: For operational commands (`make start`, `make logs`, etc.)
- **curl**: For health check testing and API testing
- **Python venv**: For local development (optional, Docker preferred)

### Configuration Dependencies

**Environment Variables** (from `env.example`):
| Variable | Required | Default | Purpose | Story |
|----------|----------|---------|---------|-------|
| `LLM_PROVIDER` | No | `grok-4` | Primary LLM provider selection | Story 2.2 |
| `GROK_API_KEY` | Yes (if provider=grok-4) | - | XAI API authentication | Story 2.2 |
| `CHATGPT_API_KEY` | Yes (if provider=chatgpt-5) | - | OpenAI API authentication | Story 2.2 |
| `REDIS_HOST` | No | `redis` | Redis hostname | Story 2.5 |
| `REDIS_PORT` | No | `6379` | Redis port | Story 2.5 |
| `MCP_SERVER_URL` | No | `http://mcp-server:8002` | MCP server endpoint | Story 2.4 |
| `BACKEND_PORT` | No | `8001` | Backend API exposed port | Story 2.1 |
| `BACKEND_URL` | No | `http://backend:8000` | Backend internal URL | Epic 5 |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity | All stories |
| `ENVIRONMENT` | No | `dev` | Environment type (dev/staging/prod) | All stories |
| `AGENTIC_MEMORIES_URL` | Yes | `http://host.docker.internal:8080` | agentic-memories endpoint | Epic 3 |

### Integration Testing Dependencies

**Testing Tools** (to be added in Epic 6):
- `pytest`: Unit and integration testing
- `pytest-asyncio`: Async test support for FastAPI
- `httpx`: Test client for API testing
- `fakeredis`: Redis mock for testing
- `responses`: HTTP mock for external API testing

## Acceptance Criteria (Authoritative)

This section provides the complete, normalized list of acceptance criteria for Epic 2. Each AC is atomic, testable, and traceable to implementation components.

### Story 2.1: Backend API Foundation

**AC 2.1.1**: FastAPI application initializes successfully with proper middleware (CORS, request logging)
- **Given**: The backend service is started
- **When**: The application initializes
- **Then**: FastAPI starts with CORS middleware and request logging middleware configured

**AC 2.1.2**: GET /health returns correct response format with 200 status
- **Given**: The backend API is running
- **When**: I call `GET /health`
- **Then**: It returns `{"status": "ok", "timestamp": "2025-11-10T12:00:00Z"}` with 200 status code (ISO 8601 timestamp)

**AC 2.1.3**: GET /health/detailed returns component health status
- **Given**: The backend API is running
- **When**: I call `GET /health/detailed`
- **Then**: It returns component health status with structure: `{"status": "ok", "components": {"mcp_server": "ok", "redis": "ok", "llm_api": "ok", "agentic_memories": "ok"}, "timestamp": "..."}`

**AC 2.1.4**: Docker health check passes validation
- **Given**: The backend API is running
- **When**: I check Docker health checks
- **Then**: The service passes health validation (`docker inspect` shows healthy status)

**AC 2.1.5**: Component failures don't fail the entire health check
- **Given**: A component is down (e.g., Redis)
- **When**: I call `/health/detailed`
- **Then**: It reflects the component status without failing the entire health check (returns 200 with degraded status)

**AC 2.1.6**: Request logging includes required fields
- **Given**: The backend API is running
- **When**: I check request logging
- **Then**: All requests are logged with method, path, status code, and response time

### Story 2.2: LLM Client Setup & Provider Management

**AC 2.2.1**: Grok-4 API authentication succeeds
- **Given**: Grok-4 API key is configured
- **When**: I initialize the LLM client
- **Then**: It authenticates and can make API calls successfully

**AC 2.2.2**: LLM client supports multiple providers with selection logic
- **Given**: The LLM client is configured
- **When**: I configure providers
- **Then**: It supports Grok-4 (primary) and ChatGPT-5 (fallback) with provider selection logic

**AC 2.2.3**: Automatic failover to ChatGPT-5 when Grok-4 fails
- **Given**: Grok-4 fails (network error, API error, rate limit)
- **When**: I call the LLM client
- **Then**: It automatically falls back to ChatGPT-5 within 2 seconds

**AC 2.2.4**: User-friendly error message when both LLMs fail
- **Given**: Both LLMs fail
- **When**: I call the LLM client
- **Then**: It returns a clear, user-friendly error message: "I'm experiencing technical difficulties. Please try again in a moment."

**AC 2.2.5**: Provider failures are logged with details
- **Given**: The LLM client encounters errors
- **When**: I check error handling
- **Then**: Provider failures are logged with error details, retry attempts, and fallback actions

**AC 2.2.6**: Rate limiting is handled gracefully
- **Given**: Rate limiting occurs
- **When**: I call the LLM client
- **Then**: It handles rate limit errors gracefully and suggests retry after appropriate delay

**AC 2.2.7**: Configuration is environment-based
- **Given**: The LLM client is configured
- **When**: I check configuration
- **Then**: API keys, base URLs, and timeouts are configurable via environment variables

### Story 2.3: SSE Streaming Support

**AC 2.3.1**: LLM streams tokens via SSE format
- **Given**: A chat request is made
- **When**: I call the LLM client with streaming enabled
- **Then**: It streams tokens via SSE format: `data: {"type":"token","content":"..."}\n\n`

**AC 2.3.2**: GET /api/stream/{conversation_id} streams continuously
- **Given**: A streaming request is made
- **When**: I call `GET /api/stream/{conversation_id}`
- **Then**: Tokens stream continuously until completion with proper SSE event formatting

**AC 2.3.3**: First token arrives within 500ms (p95)
- **Given**: Streaming is initiated
- **When**: The first token arrives
- **Then**: It arrives within 500ms (p95) of request initiation

**AC 2.3.4**: Completion event includes token usage
- **Given**: Streaming completes
- **When**: I check the response
- **Then**: It includes completion event: `{"type":"done","tokens_used":{"prompt":100,"completion":200}}`

**AC 2.3.5**: Client disconnections are handled properly
- **Given**: A client is streaming
- **When**: The client disconnects
- **Then**: The stream is properly closed and resources are cleaned up

**AC 2.3.6**: Errors during streaming send error event
- **Given**: Streaming is in progress
- **When**: An error occurs during streaming
- **Then**: An error event is sent: `{"type":"error","message":"..."}` and the stream closes gracefully

**AC 2.3.7**: Multiple concurrent streams are supported
- **Given**: Multiple clients are streaming
- **When**: I check connection management
- **Then**: Multiple concurrent streams are supported (up to 100 concurrent connections)

### Story 2.4: Function Calling for MCP Tools

**AC 2.4.1**: LLM requests tools via function calling with proper schema
- **Given**: I send a message requiring internet search ("What's the weather today?")
- **When**: The LLM processes the message
- **Then**: The LLM requests the `internet_search` tool via function calling with proper schema

**AC 2.4.2**: Backend calls MCP server tool via HTTP with JSON-RPC 2.0
- **Given**: A function call request is received
- **When**: The backend processes it
- **Then**: It calls the MCP server tool via HTTP with proper JSON-RPC 2.0 formatting

**AC 2.4.3**: Tool execution completes within 5 seconds (p95)
- **Given**: A tool call is made
- **When**: The tool executes
- **Then**: Results are returned within 5 seconds (p95) and added to LLM context

**AC 2.4.4**: Tool results are incorporated into final response
- **Given**: Tool results are received
- **When**: The LLM generates final response
- **Then**: It incorporates tool results into the answer with proper attribution

**AC 2.4.5**: Multiple tool calls are handled in sequence
- **Given**: Multiple tool calls are needed (e.g., search + memory retrieval)
- **When**: Annie processes the request
- **Then**: Tools are called in correct order and results combined appropriately

**AC 2.4.6**: Tool failures are handled gracefully
- **Given**: A tool call fails
- **When**: The tool returns an error
- **Then**: The error is handled gracefully and Annie informs the user without crashing

**AC 2.4.7**: All tools are registered with proper schemas
- **Given**: Function calling is enabled
- **When**: I check tool schemas
- **Then**: All available tools are registered with proper descriptions, parameters, and return types

### Story 2.5: Conversation State Management

**AC 2.5.1**: Session is created in Redis with proper structure
- **Given**: A user sends a message
- **When**: The backend processes it
- **Then**: A session is created in Redis with structure: `{"user_id": "12345", "platform": "telegram", "conversation_id": "conv_abc123", "created_at": "2025-11-10T12:00:00Z", "last_activity": "2025-11-10T12:00:00Z"}`

**AC 2.5.2**: Conversation history is retrieved from Redis
- **Given**: An active session exists
- **When**: The user sends another message
- **Then**: The conversation history is retrieved from Redis with all previous messages

**AC 2.5.3**: LLM uses full conversation context
- **Given**: Conversation history exists
- **When**: The LLM generates a response
- **Then**: It uses the full conversation context (up to last 20 messages or 4000 tokens, whichever is smaller)

**AC 2.5.4**: Session expires after 1 hour of inactivity
- **Given**: A session is inactive for 1 hour
- **When**: I check Redis
- **Then**: The session has expired (TTL enforced) and a new session is created on next message

**AC 2.5.5**: Conversation history API supports pagination
- **Given**: I want to retrieve conversation state
- **When**: I call `GET /api/conversations/{user_id}`
- **Then**: It returns conversation history with pagination support (max 50 messages per page)

**AC 2.5.6**: System continues when Redis connection fails
- **Given**: Redis connection fails
- **When**: A message is processed
- **Then**: The system continues without conversation context but logs the error

**AC 2.5.7**: Conversation retrieval completes within 50ms (p95)
- **Given**: Conversation state is requested
- **When**: I check performance
- **Then**: Conversation retrieval completes within 50ms (p95)

### Story 2.6: Error Handling Patterns

**AC 2.6.1**: Unhandled exceptions return user-friendly error response
- **Given**: Any API endpoint encounters an unhandled exception
- **When**: The exception occurs
- **Then**: It returns a user-friendly error response: `{"error": {"code": "INTERNAL_ERROR", "message": "Something went wrong. Please try again.", "request_id": "req_abc123"}}` with 500 status code

**AC 2.6.2**: System continues when agentic-memories is down
- **Given**: agentic-memories service is down
- **When**: External service fails
- **Then**: The system continues without memory context and logs the failure without crashing

**AC 2.6.3**: MCP server unavailability fails tool calls gracefully
- **Given**: MCP server is unavailable
- **When**: External service fails
- **Then**: Tool calls fail gracefully with clear error messages to users

**AC 2.6.4**: Rate limiting returns appropriate error with retry-after
- **Given**: LLM API rate limits are hit
- **When**: Rate limiting occurs
- **Then**: The system queues requests or returns appropriate rate limit error with retry-after header

**AC 2.6.5**: Invalid input returns 400 with validation details
- **Given**: Invalid input is provided
- **When**: Validation errors occur
- **Then**: The API returns 400 status with specific validation error details

**AC 2.6.6**: Requests timeout after 30 seconds
- **Given**: A request takes >30 seconds
- **When**: Timeout scenarios occur
- **Then**: It times out gracefully with appropriate error message

**AC 2.6.7**: Errors include request context for debugging
- **Given**: Any error occurs
- **When**: I check error logs
- **Then**: All errors include request context (user_id, conversation_id, request_id) for debugging

## Traceability Mapping

This table maps each acceptance criterion to the spec sections, implementation components, and test ideas.

| AC ID | Spec Section(s) | Component(s)/API(s) | Test Idea |
|-------|----------------|---------------------|-----------|
| **2.1.1** | Detailed Design → Services/Modules<br>NFR → Observability | `backend/api/main.py`<br>CORS middleware<br>Request logging middleware | Unit test: Verify middleware registration<br>Integration test: Check CORS headers in response |
| **2.1.2** | APIs → GET /health<br>Data Models → Error Response | `backend/api/main.py`<br>`/health` endpoint | Integration test: Call endpoint, verify JSON format and timestamp |
| **2.1.3** | APIs → GET /health/detailed<br>Workflows → Session Management | `backend/api/main.py`<br>`/health/detailed` endpoint<br>Component health functions | Integration test: Call endpoint, verify all components present<br>Mock component failures |
| **2.1.4** | System Architecture Alignment | `docker-compose.yml`<br>Health check configuration | Integration test: `docker inspect` after startup |
| **2.1.5** | NFR → Reliability<br>Workflows → Error Handling | `backend/api/main.py`<br>Component health check functions | Integration test: Stop Redis, call /health/detailed, verify 200 status |
| **2.1.6** | NFR → Observability<br>Detailed Design → Services | Request logging middleware | Integration test: Make requests, check logs for required fields |
| **2.2.1** | Dependencies → XAI API<br>Detailed Design → LLM Client | `backend/api/llm_client.py`<br>Grok-4 authentication | Unit test: Mock API, verify auth headers<br>Integration test: Real API call |
| **2.2.2** | Detailed Design → LLM Client<br>Dependencies → OpenAI API | `backend/api/llm_client.py`<br>Provider selection logic | Unit test: Test provider selection based on config |
| **2.2.3** | NFR → Reliability<br>Workflows → Provider Failover | `backend/api/llm_client.py`<br>Failover logic | Integration test: Mock Grok-4 failure, verify ChatGPT-5 call within 2s |
| **2.2.4** | Data Models → Error Response<br>NFR → Reliability | `backend/api/llm_client.py`<br>Error handling | Unit test: Mock both providers failing, verify error message |
| **2.2.5** | NFR → Observability<br>Workflows → Provider Failover | `backend/api/llm_client.py`<br>Error logging | Integration test: Trigger failures, verify log entries |
| **2.2.6** | NFR → Security<br>Data Models → Error Response | `backend/api/llm_client.py`<br>Rate limit handling | Integration test: Mock rate limit, verify retry-after header |
| **2.2.7** | Dependencies → Configuration | `backend/api/config.py`<br>`backend/api/llm_client.py` | Unit test: Verify environment variable loading |
| **2.3.1** | Data Models → LLM Response<br>APIs → GET /api/stream | `backend/api/routes/stream.py`<br>SSE streaming | Integration test: Subscribe to stream, verify SSE format |
| **2.3.2** | APIs → GET /api/stream<br>Workflows → Standard Chat Flow | `backend/api/routes/stream.py`<br>Streaming handler | Integration test: Full streaming flow, verify events |
| **2.3.3** | NFR → Performance | `backend/api/routes/stream.py`<br>`backend/api/llm_client.py` | Performance test: Measure time to first token (p95) |
| **2.3.4** | Data Models → LLM Response<br>NFR → Observability | `backend/api/routes/stream.py` | Integration test: Verify completion event includes token usage |
| **2.3.5** | Workflows → Standard Chat Flow<br>NFR → Reliability | `backend/api/routes/stream.py`<br>Connection management | Integration test: Disconnect client mid-stream, verify cleanup |
| **2.3.6** | Data Models → Error Response<br>Workflows → Error Handling | `backend/api/routes/stream.py`<br>Error handler | Integration test: Trigger error during stream, verify error event |
| **2.3.7** | NFR → Performance | `backend/api/routes/stream.py`<br>Connection pool | Load test: 100 concurrent connections, verify all succeed |
| **2.4.1** | Data Models → Function Call<br>Workflows → Function Calling | `backend/api/llm_client.py`<br>Function calling parser | Integration test: Send message requiring tool, verify function call |
| **2.4.2** | APIs → MCP Server Interface<br>Dependencies → MCP Server | `backend/api/mcp_client.py`<br>JSON-RPC 2.0 formatter | Integration test: Verify JSON-RPC request format |
| **2.4.3** | NFR → Performance<br>Workflows → Function Calling | `backend/api/mcp_client.py`<br>MCP Server tools | Performance test: Measure tool execution time (p95) |
| **2.4.4** | Workflows → Function Calling | `backend/api/llm_client.py`<br>Tool result integration | Integration test: Verify tool results in final response |
| **2.4.5** | Workflows → Function Calling | `backend/api/routes/chat.py`<br>Tool orchestration | Integration test: Message requiring multiple tools, verify sequence |
| **2.4.6** | NFR → Reliability<br>Workflows → Error Handling | `backend/api/mcp_client.py`<br>Error handler | Integration test: Mock tool failure, verify graceful handling |
| **2.4.7** | Data Models → Function Call<br>Dependencies → MCP Server | `backend/api/llm_client.py`<br>Tool schema registration | Unit test: Verify all tools registered with schemas |
| **2.5.1** | Data Models → Session Model<br>Dependencies → Redis | `backend/api/state.py`<br>Session creation | Integration test: Send message, verify Redis session structure |
| **2.5.2** | Data Models → Conversation History<br>Workflows → Session Management | `backend/api/state.py`<br>History retrieval | Integration test: Multi-message conversation, verify history |
| **2.5.3** | Workflows → Standard Chat Flow<br>NFR → Performance | `backend/api/llm_client.py`<br>Context builder | Integration test: 20-message conversation, verify context limit |
| **2.5.4** | Dependencies → Redis<br>Workflows → Session Management | Redis TTL configuration | Integration test: Wait 1 hour, verify session expired |
| **2.5.5** | APIs → GET /api/conversations | `backend/api/routes/chat.py`<br>Pagination logic | Integration test: Retrieve history with pagination |
| **2.5.6** | NFR → Reliability<br>Workflows → Error Handling | `backend/api/state.py`<br>Error handler | Integration test: Stop Redis, verify system continues |
| **2.5.7** | NFR → Performance | `backend/api/state.py`<br>Redis client | Performance test: Measure retrieval time (p95) |
| **2.6.1** | Data Models → Error Response<br>NFR → Observability | `backend/api/errors.py`<br>Global exception handler | Integration test: Trigger exception, verify error format |
| **2.6.2** | NFR → Reliability<br>Dependencies → agentic-memories | `backend/api/main.py`<br>Health check | Integration test: Mock agentic-memories down, verify continuation |
| **2.6.3** | NFR → Reliability<br>Dependencies → MCP Server | `backend/api/mcp_client.py` | Integration test: Stop MCP server, verify graceful failure |
| **2.6.4** | NFR → Security<br>Data Models → Error Response | `backend/api/llm_client.py`<br>Rate limit handler | Integration test: Mock rate limit, verify 429 + retry-after |
| **2.6.5** | Data Models → Error Response<br>NFR → Security | FastAPI validation<br>`backend/api/routes/*` | Integration test: Send invalid payload, verify 400 response |
| **2.6.6** | NFR → Reliability | Request timeout configuration | Integration test: Mock slow endpoint, verify 30s timeout |
| **2.6.7** | NFR → Observability | `backend/api/errors.py`<br>Logging | Integration test: Trigger errors, verify log context fields |

## Risks, Assumptions, Open Questions

### Risks

**RISK-1: LLM API Rate Limiting and Costs**
- **Description**: Grok-4 and ChatGPT-5 APIs may have rate limits or high costs during development and production
- **Impact**: Service degradation, development delays, budget overruns
- **Probability**: Medium
- **Mitigation**:
  - Implement rate limiting and request queuing (Story 2.6 AC#4)
  - Monitor API usage and costs during development
  - Use fallback provider to distribute load
  - Implement caching for repeated queries (if applicable)
- **Status**: Mitigation planned in Story 2.6

**RISK-2: LLM Provider Failover Performance**
- **Description**: Failover from Grok-4 to ChatGPT-5 within 2 seconds may be challenging with network latency
- **Impact**: Degraded user experience, missed performance SLA (<2s p95 response time)
- **Probability**: Medium
- **Mitigation**:
  - Implement fast failure detection (timeout = 1-2 seconds)
  - Pre-warm ChatGPT-5 connections to reduce failover latency
  - Use async I/O for parallel provider checks
  - Monitor failover times in production
- **Status**: Implementation details in Story 2.2

**RISK-3: Redis Memory Limits**
- **Description**: Redis may run out of memory with high conversation volume (1-hour session TTL, 30-minute conversation TTL)
- **Impact**: Service degradation, session/conversation loss
- **Probability**: Low-Medium
- **Mitigation**:
  - Configure Redis maxmemory policy (e.g., allkeys-lru)
  - Monitor Redis memory usage
  - Adjust TTL values based on usage patterns
  - Use Redis persistence (AOF) to recover from restarts
- **Status**: Configuration in docker-compose.yml, monitoring TBD

**RISK-4: SSE Connection Stability**
- **Description**: SSE connections may be unstable over poor networks or with Telegram long-polling
- **Impact**: Broken streaming responses, poor user experience
- **Probability**: Medium
- **Mitigation**:
  - Implement reconnection logic in Telegram bot (Epic 5)
  - Add connection timeouts and heartbeats
  - Fall back to non-streaming responses if SSE fails
  - Test SSE stability under various network conditions
- **Status**: Epic 5 implementation, Story 2.3 handles disconnections

**RISK-5: Function Calling Schema Compatibility**
- **Description**: Grok-4 and ChatGPT-5 may have different function calling schemas or behavior
- **Impact**: Tool calls may fail when using fallback provider
- **Probability**: Low
- **Mitigation**:
  - Test function calling with both providers
  - Normalize function calling schemas to OpenAI standard
  - Handle provider-specific differences in LLM client
  - Document known incompatibilities
- **Status**: Testing in Story 2.4

**RISK-6: Missing Automated Tests**
- **Description**: Epic 2 stories may be implemented without comprehensive test coverage (Technical Debt item)
- **Impact**: Regressions, difficult refactoring, lower code quality
- **Probability**: High (already identified in Story 2.1 review)
- **Mitigation**:
  - Document as technical debt item
  - Add tests incrementally during Epic 2 implementation
  - Prioritize critical path testing (LLM client, streaming, state management)
  - Address in Epic 6 (Integration & Quality)
- **Status**: Documented in docs/TECHNICAL_DEBT.md

### Assumptions

**ASSUMPTION-1: XAI API Compatibility**
- **Description**: Grok-4 API is assumed to be OpenAI-compatible for chat completions and function calling
- **Validation**: Verify API compatibility during Story 2.2 implementation
- **Impact if False**: May require custom LLM client implementation for Grok-4
- **Status**: To be validated

**ASSUMPTION-2: Redis Capacity Sufficient**
- **Description**: Single Redis instance can handle conversation state for expected user volume (V1.0 MVP)
- **Validation**: Monitor Redis performance under load testing
- **Impact if False**: May need Redis clustering or sharding
- **Status**: To be validated in production

**ASSUMPTION-3: MCP Server HTTP Transport Performance**
- **Description**: HTTP transport for MCP server (refactored in Epic 1) has acceptable latency (<1s average for tool calls)
- **Validation**: Measure tool call latency in Story 2.4
- **Impact if False**: May need to optimize MCP client or revert to stdio transport
- **Status**: To be validated

**ASSUMPTION-4: SSE Compatible with Telegram Bot**
- **Description**: Telegram Bot can consume SSE streams and forward to users in real-time
- **Validation**: Test SSE consumption in Epic 5 implementation
- **Impact if False**: May need alternative streaming mechanism (WebSockets, polling)
- **Status**: To be validated in Epic 5

**ASSUMPTION-5: Conversation Context Limit Sufficient**
- **Description**: Last 20 messages or 4000 tokens provides sufficient context for LLM responses
- **Validation**: User testing and feedback during development
- **Impact if False**: May need to adjust limits or implement smart context truncation
- **Status**: To be validated with user feedback

**ASSUMPTION-6: No User Authentication Required**
- **Description**: V1.0 relies on Telegram's user authentication (no separate auth system needed)
- **Validation**: Confirmed in PRD and Architecture Plan
- **Impact if False**: Would require significant architecture changes
- **Status**: Validated (per PRD constraints)

### Open Questions

**QUESTION-1: LLM Temperature and Model Parameters**
- **Question**: What temperature and other LLM parameters should be used for optimal decision-making advice?
- **Impact**: Affects response quality and consistency
- **Next Step**: Experiment with temperature values (0.7 default, test 0.5-0.9 range) during Story 2.2
- **Owner**: Dev team + User feedback

**QUESTION-2: Function Calling Schema Design**
- **Question**: Should function schemas be defined in backend or MCP server? How to keep them in sync?
- **Impact**: Affects maintainability and schema consistency
- **Next Step**: Define schema ownership pattern in Story 2.4 (recommend: MCP server provides schemas via /tools/list)
- **Owner**: Architect + Dev team

**QUESTION-3: Conversation History Storage Strategy**
- **Question**: Should conversation history be stored in Redis (temporary) or PostgreSQL (persistent) for V1.0?
- **Impact**: Affects data persistence and user experience
- **Next Step**: Confirm Redis-only approach per Architecture Plan (PostgreSQL deferred to V2.0)
- **Owner**: Architect (already decided per Architecture Plan)
- **Status**: **ANSWERED** - Redis-only for V1.0, PostgreSQL in V2.0

**QUESTION-4: Rate Limiting Strategy**
- **Question**: Should rate limiting be per-user, per-IP, or global? What are the limits?
- **Impact**: Affects user experience and resource management
- **Next Step**: Define rate limiting strategy in Story 2.6 based on LLM provider limits
- **Owner**: Dev team + Product

**QUESTION-5: Error Message Localization**
- **Question**: Should error messages support multiple languages, or English-only for V1.0?
- **Impact**: Affects international user experience
- **Next Step**: Confirm English-only for V1.0 (internationalization deferred to future versions)
- **Owner**: Product
- **Status**: **ANSWERED** - English-only for V1.0

**QUESTION-6: Streaming Fallback Mechanism**
- **Question**: If SSE streaming fails, should the system fall back to synchronous responses?
- **Impact**: Affects reliability and user experience
- **Next Step**: Implement fallback in Story 2.3 (return full response if streaming fails)
- **Owner**: Dev team

## Test Strategy Summary

### Test Levels

**Unit Testing** (to be added - Technical Debt):
- **Scope**: Individual functions and classes in isolation
- **Framework**: pytest
- **Coverage Target**: 80%+ for critical components (LLM client, state manager, error handler)
- **Focus Areas**:
  - LLM client: Provider selection, failover logic, function calling parsing
  - State manager: Session creation, conversation retrieval, TTL handling
  - Error handler: Exception catching, error formatting, logging
  - MCP client: JSON-RPC formatting, response parsing
- **Mocking**: Use pytest mocks for external APIs (LLM, Redis, MCP server)

**Integration Testing** (to be added - Technical Debt):
- **Scope**: Component interactions and API endpoints
- **Framework**: pytest + httpx.AsyncClient
- **Coverage Target**: All API endpoints, all workflows
- **Focus Areas**:
  - API endpoints: Health checks, chat, streaming, conversation history
  - LLM integration: Actual API calls to Grok-4 and ChatGPT-5 (with test keys)
  - Redis integration: Session/conversation CRUD operations
  - MCP integration: Tool calls via HTTP
  - Error scenarios: Component failures, timeouts, rate limits
- **Test Data**: Use test fixtures for conversations, sessions, tool responses

**Performance Testing** (Epic 6):
- **Scope**: Latency, throughput, and scalability validation
- **Tools**: pytest-benchmark, locust, or custom scripts
- **Metrics to Validate**:
  - First token latency: <500ms (p95) - Story 2.3 AC#3
  - Total response time: <2s (p95) - Story 2.2, 2.3
  - Conversation retrieval: <50ms (p95) - Story 2.5 AC#7
  - Tool execution: <5s (p95) - Story 2.4 AC#3
  - Concurrent SSE streams: 100 connections - Story 2.3 AC#7
- **Load Scenarios**: Simulate realistic user load (15+ messages/user/day)

**End-to-End Testing** (Epic 6):
- **Scope**: Complete user flows from Telegram bot to backend to LLM
- **Framework**: pytest + Telegram Bot test client
- **Scenarios**:
  - Standard chat flow (no tools)
  - Chat with function calling (tool invocation)
  - Provider failover (Grok-4 failure → ChatGPT-5)
  - Error handling (Redis down, MCP server down)
  - Streaming disconnection and reconnection
- **Environment**: Docker Compose with all services running

### Test Coverage by Story

| Story | Unit Tests | Integration Tests | Performance Tests | E2E Tests |
|-------|-----------|-------------------|-------------------|-----------|
| **2.1** | Middleware, health check functions | Health endpoints, Docker health check | API response time | - |
| **2.2** | Provider selection, failover logic | LLM API calls, provider failover | Failover time (<2s) | Chat with failover |
| **2.3** | SSE formatter | Streaming endpoints, disconnections | First token latency, concurrent streams | Full streaming flow |
| **2.4** | JSON-RPC formatter, schema parser | MCP tool calls, function calling flow | Tool execution time | Chat with tool usage |
| **2.5** | Session/conversation models | Redis CRUD, conversation history API | Conversation retrieval time | Multi-message conversation |
| **2.6** | Error formatters | All error scenarios (component failures, timeouts) | - | Error recovery flows |

### Acceptance Criteria Testing

Each of the 42 acceptance criteria will be validated through tests as defined in the Traceability Mapping table:
- **Unit tests**: 15 ACs (component-level validation)
- **Integration tests**: 35 ACs (API and workflow validation)
- **Performance tests**: 7 ACs (latency and throughput validation)
- **Load tests**: 1 AC (concurrent connections)

### Test Data Strategy

**Mock Data**:
- LLM responses: Pre-defined token streams and completion events
- Tool responses: Mock internet search results, memory data
- Error scenarios: Network timeouts, API rate limits, invalid inputs

**Test Fixtures** (`tests/fixtures/`):
- `conversations.json`: Sample conversation histories
- `sessions.json`: Sample Redis session data
- `tool_schemas.json`: MCP tool definitions
- `llm_responses.json`: Sample LLM API responses

**Test Environments**:
- **Local Development**: Docker Compose with all services
- **CI/CD**: GitHub Actions with Docker Compose (Epic 6)
- **Staging**: Production-like environment for integration testing (future)

### Edge Cases and Error Scenarios

**Critical Edge Cases to Test**:
1. **Simultaneous provider failures**: Both Grok-4 and ChatGPT-5 down (AC 2.2.4)
2. **Redis failover during conversation**: Redis fails mid-conversation (AC 2.5.6, 2.6.2)
3. **SSE disconnection during streaming**: Client disconnects before completion (AC 2.3.5)
4. **Function calling loops**: LLM requests same tool repeatedly (need safeguard)
5. **Conversation context limit**: Exactly 20 messages or 4000 tokens (AC 2.5.3)
6. **Concurrent tool calls**: Multiple tools requested simultaneously (AC 2.4.5)
7. **Rate limit at high load**: All users hit rate limit simultaneously (AC 2.6.4)
8. **Session expiration edge**: Session expires exactly during message processing (AC 2.5.4)

### Test Execution Plan

**During Epic 2 Implementation**:
1. **Story 2.1**: Add integration tests for health endpoints (Technical Debt - add unit tests later)
2. **Story 2.2**: Add integration tests for LLM client, prioritize failover testing
3. **Story 2.3**: Add integration tests for streaming, performance tests for latency
4. **Story 2.4**: Add integration tests for function calling, MCP integration
5. **Story 2.5**: Add integration tests for state management, Redis operations
6. **Story 2.6**: Add integration tests for all error scenarios

**During Epic 6 (Integration & Quality)**:
- Add comprehensive unit test suite (addressing Technical Debt)
- Add end-to-end test suite for all user flows
- Add performance and load testing
- Achieve 80%+ test coverage for critical components
- Set up CI/CD pipeline with automated testing

### Test Tools and Frameworks

**Required Dependencies** (to be added):
- `pytest>=7.4.0` - Test framework
- `pytest-asyncio>=0.21.0` - Async test support
- `pytest-cov>=4.1.0` - Coverage reporting
- `httpx>=0.25.0` - HTTP test client (already installed)
- `fakeredis>=2.20.0` - Redis mock for testing
- `responses>=0.24.0` - HTTP mock for external APIs
- `pytest-benchmark>=4.0.0` - Performance testing (optional)

**Test Execution**:
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=backend/api --cov-report=html

# Run specific story tests
pytest tests/test_llm_client.py -v

# Run performance tests only
pytest tests/performance/ -v
```
