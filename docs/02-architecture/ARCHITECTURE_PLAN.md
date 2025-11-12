# Architecture Plan

## Overview

This document defines the system architecture for Annie chatbot, covering service design, data flow, state management, and communication patterns.

## System Architecture

### High-Level Architecture

```
┌─────────────────┐
│  Telegram Bot   │
│   (Container)   │
└────────┬────────┘
         │ HTTP
         ▼
┌─────────────────┐
│  Backend API    │
│   (Container)   │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌────────┐ ┌──────────┐
│  Redis │ │   MCP    │
│        │ │  Server  │
└────────┘ └────┬─────┘
                │ Docker Exec
                ▼
         ┌─────────────┐
         │   Tools     │
         │ - Internet  │
         │ - Memories  │
         └──────┬──────┘
                │
         ┌──────┴──────┐
         │             │
         ▼             ▼
    ┌─────────┐  ┌──────────────┐
    │  Brave  │  │ agentic-     │
    │  Search │  │ memories     │
    └─────────┘  └──────────────┘
```

## Service Architecture

### Backend API Service

**Technology**: FastAPI (Python 3.12+)

**Responsibilities**:
- Handle HTTP requests from Telegram bot
- Manage conversation state
- Call LLM APIs
- Orchestrate MCP tool calls
- Stream responses via SSE
- Manage user sessions

**Key Components**:
- **LLM Client**: Unified client for Grok-4/ChatGPT-5
- **MCP Client**: Docker exec wrapper for MCP communication
- **State Manager**: Redis/PostgreSQL state management
- **Streaming Handler**: SSE response streaming

**Endpoints**:
- `POST /api/chat` - Process chat message
- `GET /api/stream/{conversation_id}` - Stream LLM response
- `GET /health` - Health check
- `GET /api/conversations/{user_id}` - Get conversation history

### MCP Server Service

**Technology**: Python MCP SDK

**Responsibilities**:
- Host MCP tools
- Execute tool calls
- Manage tool lifecycle
- Provide tool schemas

**Tools**:
1. **internet_search** - Search web via Brave Search
2. **store_memory** - Store conversation in agentic-memories
3. **retrieve_memories** - Retrieve memories from agentic-memories
4. **get_portfolio_summary** - Get portfolio data

**Communication**:
- Stdio transport
- Called via Docker exec from backend
- JSON-RPC 2.0 protocol

### Telegram Bot Service

**Technology**: python-telegram-bot

**Responsibilities**:
- Poll Telegram API for updates
- Forward messages to backend API
- Stream responses to users
- Handle Telegram-specific features

**Features**:
- Long polling (V1)
- Message splitting for long responses
- Error handling and retries

### Redis Service

**Technology**: Redis 7.2

**Responsibilities**:
- Session state storage
- Conversation cache
- Rate limiting counters
- Real-time state synchronization

**Data Structures**:
- Strings: Session data, cached responses
- Hashes: User state
- Lists: Message queues
- Sets: Active users

### PostgreSQL Service (Future)

**Technology**: PostgreSQL 16+

**Responsibilities**:
- Persistent conversation history
- User preferences
- Affection scores
- Analytics data

**Note**: PostgreSQL can be added in V1.1 or later

## Data Flow

### Message Flow

```
1. User sends message via Telegram
   ↓
2. Telegram Bot receives update
   ↓
3. Telegram Bot forwards to Backend API: POST /api/chat
   ↓
4. Backend API:
   - Loads conversation state from Redis
   - Detects if tools needed (via LLM function calling)
   - Calls MCP Server tools if needed
   ↓
5. MCP Server executes tools:
   - internet_search → Brave Search API
   - retrieve_memories → agentic-memories API
   ↓
6. Backend API:
   - Constructs LLM context with tool results
   - Calls LLM API (Grok-4 or ChatGPT-5)
   - Streams response via SSE
   ↓
7. Telegram Bot:
   - Receives streamed response
   - Sends to user incrementally
   ↓
8. Backend API:
   - Stores conversation in Redis
   - Stores memory via MCP → agentic-memories
   - Updates session state
```

### Tool Call Flow

```
1. LLM decides to call tool (function calling)
   ↓
2. Backend API receives tool call request
   ↓
3. Backend API calls MCP Client
   ↓
4. MCP Client uses Docker exec:
   docker exec annie-mcp-server python -c "..."
   ↓
5. MCP Server executes tool
   ↓
6. Tool calls external API (Brave, agentic-memories)
   ↓
7. Tool result returned to MCP Server
   ↓
8. MCP Server returns result via stdio
   ↓
9. MCP Client parses result
   ↓
10. Backend API receives tool result
    ↓
11. Backend API adds tool result to LLM context
    ↓
12. LLM generates final response
```

## State Management Architecture

### State Storage Strategy

**Hot Data (Redis)**:
- Active sessions (TTL: 1 hour)
- Conversation cache (TTL: 30 minutes)
- Rate limiting counters
- Real-time state

**Cold Data (PostgreSQL - Future)**:
- Conversation history (permanent)
- User preferences (permanent)
- Affection scores (permanent)
- Analytics data

### State Synchronization

**Pattern**: Eventual consistency

```
Platform A updates state
    ↓
Redis updated immediately
    ↓
PostgreSQL updated (async) - Future
    ↓
Other platforms notified (async) - Future
    ↓
All platforms eventually consistent
```

### Session Management

**Session Lifecycle**:
1. **Creation**: On first message
2. **Update**: On each message
3. **Expiration**: After 1 hour inactivity
4. **Cleanup**: Automatic via Redis TTL

**Session Data**:
```python
{
    "user_id": "user_123",
    "platform": "telegram",
    "session_id": "session_abc",
    "conversation_id": "conv_xyz",
    "started_at": "2025-01-XXT00:00:00Z",
    "last_activity": "2025-01-XXT00:05:00Z",
    "message_count": 15
}
```

## Communication Patterns

### Backend ↔ MCP Server

**Pattern**: Docker Exec

**Implementation**:
```python
async def call_mcp_tool(tool_name: str, arguments: dict):
    cmd = [
        "docker", "exec", "-i", "annie-mcp-server",
        "python", "-c", f"""
import json
from mcp_server.tools import {tool_name}
result = {tool_name}({json.dumps(arguments)})
print(json.dumps(result))
"""
    ]
    process = await asyncio.create_subprocess_exec(...)
    stdout, stderr = await process.communicate()
    return json.loads(stdout.decode())
```

**Future**: HTTP Bridge for better performance

### Backend ↔ Telegram Bot

**Pattern**: HTTP REST API

**Implementation**:
- Telegram Bot → Backend: `POST /api/chat`
- Backend → Telegram Bot: Streaming via SSE, Telegram Bot polls

**Future**: WebSocket for bidirectional communication

### Backend ↔ LLM APIs

**Pattern**: HTTP with SSE Streaming

**Implementation**:
- Grok-4: `https://api.x.ai/v1/chat/completions`
- ChatGPT-5: `https://api.openai.com/v1/chat/completions`
- Streaming: SSE format
- Fallback: Automatic on errors

### Backend ↔ External Services

**Pattern**: HTTP via MCP Tools

**Implementation**:
- Brave Search: Via internet_search tool
- agentic-memories: Via memories tool
- Rate limiting: Client-side
- Caching: Redis cache layer

## Error Handling Strategy

### Error Types

1. **Transient Errors**: Retry with exponential backoff
2. **Rate Limit Errors**: Wait and retry
3. **Service Unavailable**: Fallback or graceful degradation
4. **Invalid Input**: Return error to user
5. **Timeout**: Retry or return timeout error

### Error Handling Flow

```
Error occurs
    ↓
Log error with context
    ↓
Determine error type
    ↓
Apply error handling strategy:
- Retry (transient errors)
- Fallback (service unavailable)
- Return error (invalid input)
    ↓
Update metrics
    ↓
Return appropriate response
```

## Scalability Considerations

### Horizontal Scaling

**Backend API**:
- Stateless design
- Scale via multiple instances
- Load balancer required

**MCP Server**:
- Can scale independently
- Stateless tool execution
- Shared Redis for state

**Telegram Bot**:
- Single instance sufficient for V1
- Can scale if needed

### Vertical Scaling

**Resource Allocation**:
- Backend: 2 vCPU, 4GB RAM
- MCP Server: 1 vCPU, 2GB RAM
- Telegram Bot: 1 vCPU, 1GB RAM
- Redis: 1 vCPU, 2GB RAM

### Future Scaling

- Add PostgreSQL for persistence
- Implement connection pooling
- Add CDN for static assets
- Implement caching layers

## Security Architecture

### Authentication

**V1**: No authentication (internal services)

**Future**:
- API key authentication
- JWT tokens
- OAuth 2.0

### Network Security

**Docker Network**:
- Isolated `annie-network`
- Services communicate via service names
- External access only via exposed ports

### Data Security

**Secrets Management**:
- Environment variables (V1)
- Docker secrets (Future)
- Cloud secret managers (Production)

**Data Encryption**:
- HTTPS for external APIs
- TLS for internal communication (Future)

## Monitoring Architecture

### Logging

**Structured Logging**:
- JSON format
- Service identification
- Request tracing
- Error context

**Log Aggregation**:
- Docker logs (V1)
- Centralized logging (Future)

### Metrics

**Key Metrics**:
- Request rate
- Response latency
- Error rate
- Tool call success rate
- Token usage
- Active users

**Metrics Collection**:
- Prometheus (Future)
- Custom metrics endpoint (V1)

### Health Checks

**Health Check Endpoints**:
- `/health` - Basic health
- `/health/detailed` - Component health

**Docker Health Checks**:
- All services have health checks
- Automatic restart on failure

## References

- DOCKER_ARCHITECTURE_RESEARCH.md: Docker setup details
- STATE_MANAGEMENT_RESEARCH.md: State management patterns
- REALTIME_COMMUNICATION_RESEARCH.md: Streaming patterns
- PRODUCTION_DEPLOYMENT_RESEARCH.md: Production considerations

