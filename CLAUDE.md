# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Annie is a personal AI companion chatbot that provides decision-making support through intelligent, context-aware advice. The system uses advanced LLM integration (Grok-4 or ChatGPT-5), persistent memory via agentic-memories, and real-time information access through MCP (Model Context Protocol) tools.

**Current Status**: V1.0 MVP - Implementation in progress. Foundation infrastructure (Story 1.1) is complete. The project uses Docker Compose to orchestrate multiple services.

## Architecture

Annie uses a microservices architecture with three main services:

### Service Communication Flow
```
Telegram Bot (User Interface)
    ↓ HTTP
Backend API (Chat Logic + LLM Integration)
    ↓ Docker Exec (stdio)
MCP Server (Tool Hosting)
    ↓ HTTP APIs
External Services (Brave Search, agentic-memories)
```

### Backend API (`backend/`)
- **Technology**: FastAPI (Python 3.12+)
- **Purpose**: HTTP API handling chat requests, LLM integration, state management
- **Communication**: Calls MCP server via Docker exec using stdio transport
- **Key Endpoints**:
  - `POST /api/chat` - Process chat messages
  - `GET /api/stream/{conversation_id}` - Stream LLM responses (SSE)
  - `GET /health` - Health check
- **Dependencies**: Redis for state management, MCP server for tool execution

### MCP Server (`mcp_server/`)
- **Technology**: Python MCP SDK
- **Purpose**: Host and execute MCP tools following JSON-RPC 2.0 protocol
- **Communication**: Stdio transport, invoked via Docker exec from backend
- **Tools** (planned):
  - `internet_search` - Web search via Brave Search API
  - `store_memory` / `retrieve_memories` - agentic-memories integration
  - `get_portfolio_summary` - Stock portfolio data
- **Current Implementation**: Basic server framework with health check tool

### Telegram Bot (`telegram_bot/`)
- **Technology**: python-telegram-bot
- **Purpose**: User interface via Telegram messaging
- **Communication**: Polls Telegram API, forwards messages to Backend API via HTTP
- **Features**: Streams LLM responses back to users

### Redis
- **Purpose**: State management and session storage
- **Configuration**: Persistent storage with AOF (append-only file)

## Development Commands

### Starting and Stopping Services

```bash
# Start all services (checks Docker, validates .env, starts containers)
make start
# OR
./scripts/run_docker.sh

# Stop all services gracefully
make stop

# Restart services
make restart

# Rebuild containers (after dependency changes)
make rebuild
```

### Viewing Logs

```bash
# View logs from all services
make logs

# View logs from specific service
make logs SERVICE=backend
make logs SERVICE=mcp-server
make logs SERVICE=telegram-bot
make logs SERVICE=redis
```

### Health Checks and Debugging

```bash
# Check service health status
make health

# Access service shell for debugging
make shell SERVICE=backend
make shell SERVICE=mcp-server
make shell SERVICE=telegram-bot
```

### Testing

```bash
# Run test suite (when implemented)
make test

# Run tests for specific service
docker compose exec backend python -m pytest tests/
docker compose exec mcp-server python -m pytest tests/
docker compose exec telegram-bot python -m pytest tests/
```

### Cleanup

```bash
# Clean up Docker resources (containers, volumes, build artifacts)
make clean
```

## Environment Configuration

### Setup
1. Copy `env.example` to `.env`: `cp env.example .env`
2. Fill in required API keys and tokens (replace `REPLACE_ME` values)
3. The `run_docker.sh` script will validate and prompt for missing values

### Required Variables
- `TELEGRAM_BOT_TOKEN` - Get from [@BotFather](https://t.me/BotFather)
- `AGENTIC_MEMORIES_URL` - agentic-memories service URL (default: `http://host.docker.internal:8080`)
- `GROK_API_KEY` - Required if `LLM_PROVIDER=grok-4` (default)
- `CHATGPT_API_KEY` - Required if `LLM_PROVIDER=chatgpt-5`
- `BRAVE_SEARCH_API_KEY` - Required for internet access tool
- `STOCK_API_KEY` - Required for stock trader tool

### Optional Variables (with defaults)
- `LLM_PROVIDER` - Primary LLM: `grok-4` (default) or `chatgpt-5`
- `ENVIRONMENT` - Environment type: `dev` (default), `staging`, `prod`
- `LOG_LEVEL` - Logging level: `DEBUG`, `INFO` (default), `WARNING`, `ERROR`, `CRITICAL`
- `BACKEND_PORT` - Backend API port (default: `8000`)
- `REDIS_HOST` / `REDIS_PORT` - Redis connection (defaults: `redis:6379`)
- `GROK_LIVE_SEARCH_MODE` - Grok-4 Live Search mode: `auto` (default), `on`, `off`
- `GROK_LIVE_SEARCH_MAX_RESULTS` - Max search results per query (default: `10`, range: 1-50)
- `GROK_LIVE_SEARCH_COST_ALERT_THRESHOLD` - Monthly cost alert threshold in USD (default: `800`)

### Security
- API keys and tokens are automatically masked in logs (shows only first 4 and last 4 characters)
- Never commit `.env` file (already in `.gitignore`)
- Environment validation happens on service startup

## MCP Server Communication

The Backend API communicates with MCP Server using Docker exec with stdio transport:

```python
# Backend invokes MCP server like this:
docker exec -i mcp-server python -m mcp_server.server
```

The communication follows JSON-RPC 2.0 protocol:
- **Request**: `{"jsonrpc": "2.0", "method": "tools/call", "params": {...}, "id": 1}`
- **Response**: `{"jsonrpc": "2.0", "result": {...}, "id": 1}`

Key MCP methods:
- `tools/list` - Get available tools and their schemas
- `tools/call` - Execute a tool with given parameters

## Code Organization

### Backend API Structure
```
backend/
├── api/
│   ├── config.py          # Environment config and validation
│   ├── logging.py         # Structured logging setup
│   └── main.py            # FastAPI application (to be implemented)
├── requirements.txt       # Python dependencies
└── Dockerfile            # Container definition
```

### MCP Server Structure
```
mcp_server/
├── server.py             # MCP server with JSON-RPC 2.0 handling
├── tools.py              # Tool registry and implementations
├── config.py             # Environment config
├── logging.py            # Structured logging
├── __init__.py
├── requirements.txt      # Python dependencies
└── Dockerfile           # Container definition
```

### Telegram Bot Structure
```
telegram_bot/
├── config.py             # Environment config
├── logging.py            # Structured logging
├── bot.py                # Bot implementation (to be implemented)
├── requirements.txt      # Python dependencies
└── Dockerfile           # Container definition
```

## Logging Standards

All services use structured logging with the following conventions:

- **Levels**: DEBUG (dev), INFO (default), WARNING, ERROR, CRITICAL
- **Format**: JSON for production, readable text for development
- **Sensitive Data**: API keys automatically masked in logs (e.g., `secr...2345`)
- **Request Tracking**: All requests include `request_id` for tracing
- **Performance**: Tool calls include `duration_ms` for monitoring

Example structured log:
```python
logger.info(
    "Tool call completed",
    extra={
        "request_id": "abc123",
        "tool_name": "internet_search",
        "duration_ms": 145,
        "result": {...}
    }
)
```

## LLM Observability with Langfuse

Annie uses [Langfuse](https://langfuse.com) for comprehensive LLM observability and tracing.

### Features
- **Automatic Tracing**: All LLM calls, tool executions, and memory operations traced via `@observe()` decorators
- **Cost Tracking**: Automatic cost calculation based on model usage and token counts
- **Session Linking**: Chat and stream requests linked via `conversation_id` for unified trace views
- **Performance Monitoring**: Track latency, token usage, and completion rates
- **Fire-and-Forget**: Tracing failures never block application flow

### Configuration
Required environment variables in `.env`:
```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...     # Your Langfuse public key
LANGFUSE_SECRET_KEY=sk-lf-...     # Your Langfuse secret key
LANGFUSE_HOST=https://us.cloud.langfuse.com  # Langfuse Cloud URL
```

### Architecture
- **Trace Hierarchy**: `chat_request` → `stream_request` → `llm_streaming` → `mcp_tool_call`
- **Session Grouping**: Traces linked by `session_id` (conversation_id) for end-to-end visibility
- **Decorator Pattern**: Functions traced with `@observe(name="...", as_type="trace"|"span")`
- **Automatic Capture**: Inputs, outputs, duration, errors, and metadata captured automatically

### Traced Components
1. **Chat Endpoint** (`backend/api/routes/chat.py`): Request handling, session management
2. **Stream Endpoint** (`backend/api/routes/stream.py`): SSE streaming, tool orchestration
3. **LLM Calls** (`backend/api/llm_client.py`): Token usage, model performance, costs
4. **Tool Execution** (`backend/api/mcp_client.py`): MCP tool calls with arguments and results
5. **Memory Storage** (`backend/api/memory.py`): Conversation memory operations
6. **Profile Management** (`backend/api/profile.py`): User profile cache and refresh

### Health Check
Check full system status via `/health/full` endpoint:
```bash
curl http://localhost:8001/health/full
```

Returns:
```json
{
  "status": "ok",
  "components": {
    "mcp_server": "ok",
    "redis": "ok",
    "llm_api": "ok",
    "agentic_memories": {
      "status": "ok",
      "checks": {
        "chroma": {"ok": true},
        "timescale": {"ok": true},
        "neo4j": {"ok": true},
        "redis": {"ok": true},
        "langfuse": {"ok": true, "enabled": true}
      }
    },
    "langfuse": {
      "enabled": true,
      "client_available": true,
      "last_flush": null
    }
  },
  "timestamp": "2025-12-21T04:31:59.857651Z"
}
```

### Viewing Traces
1. Navigate to https://us.cloud.langfuse.com
2. Filter by:
   - **Release**: `annie-dev` (or `annie-prod`)
   - **Session ID**: Conversation ID for linked traces
   - **User ID**: Telegram user ID
3. View trace hierarchy with nested spans for complete request flow

For detailed troubleshooting, see `LANGFUSE_DEBUG.md`.

## Development Workflow

When implementing new features:

1. **Check Documentation**: Review `docs/04-implementation/` for implementation plans and task breakdowns
2. **Follow Sprint Plan**: Reference `docs/04-implementation/SPRINT_PLAN.md` for epic/story organization
3. **Environment First**: Always validate `.env` configuration before coding
4. **Service-by-Service**: Implement features in one service at a time, test with Docker
5. **MCP Tools**: New tools go in `mcp_server/tools.py` with proper schema definitions
6. **Health Checks**: Every service includes health check endpoint/validation
7. **Testing**: Use `make test` or Docker exec to run tests within containers

## Docker Compose Services

Service dependencies and startup order:
1. **redis** - Starts first (data store)
2. **mcp-server** - Starts after redis (tool hosting)
3. **backend** - Starts after redis and mcp-server (API logic)
4. **telegram-bot** - Starts after backend (user interface)

All services have health checks and restart policies (`unless-stopped`).

## Python Version and Dependencies

- **Required**: Python 3.12+
- **Backend**: FastAPI, Redis client, HTTP client (implementation in progress)
- **MCP Server**: `mcp>=0.1.0`, `requests>=2.31.0`
- **Telegram Bot**: python-telegram-bot (implementation in progress)

When adding dependencies, update the service's `requirements.txt` and rebuild with `make rebuild`.

## Common Patterns

### Environment Variable Access
```python
from api.config import get_config

config = get_config()
api_key = config["GROK_API_KEY"]  # Already validated and loaded
```

### Adding a New MCP Tool
```python
# In mcp_server/tools.py
def my_new_tool(param1: str, param2: int) -> dict:
    """Tool description."""
    # Implementation
    return {"status": "success", "result": ...}

# Register tool with schema
registry.register(my_new_tool, schema={
    "name": "my_new_tool",
    "description": "Tool description",
    "inputSchema": {
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "..."},
            "param2": {"type": "integer", "description": "..."}
        },
        "required": ["param1", "param2"]
    }
})
```

### Error Handling
- All services validate environment variables on startup
- MCP server returns JSON-RPC error codes (-32700 parse error, -32601 method not found, -32603 internal error)
- Sensitive values are masked in error messages and logs

## Key Documentation

- **Product Requirements**: `docs/01-product/PRODUCT_REQUIREMENTS.md`
- **Architecture**: `docs/02-architecture/ARCHITECTURE_PLAN.md`
- **Epic/Story Breakdown**: `docs/epics-and-stories.md`
- **Sprint Plan**: `docs/04-implementation/SPRINT_PLAN.md`
- **Implementation Details**: `docs/04-implementation/V1_DETAILED_TASKS.md`
- **Deployment**: `docs/05-deployment/DEPLOYMENT_PLAN.md`
- **Contributing**: `CONTRIBUTING.md`

## External Services

- **agentic-memories**: Memory management service (must be running separately)
  - Default URL: `http://host.docker.internal:8080`
  - Used for storing and retrieving conversation memories
  - **Memory Storage Integration** (Story 3.1 - Implemented):
    - Conversations automatically stored when user sends farewell ("thanks", "bye", etc.)
    - LLM-powered summarization extracts decisions, preferences, and topics
    - Graceful degradation: Falls back to Redis queue if service unavailable
    - Background retry worker processes failed storage attempts every 5 minutes
    - Circuit breaker: Pauses after 5 consecutive failures for 15 minutes
    - Memory Object includes:
      - Conversation summary (2-3 sentences)
      - Decisions made (with options considered and reasoning)
      - User preferences (risk tolerance, priorities, constraints)
      - Topics discussed
      - Overall sentiment
  - **Technical Details**:
    - Backend module: `backend/api/memory.py` (MemoryManager)
    - HTTP client: `backend/api/memory_client.py` (MemoryClient)
    - MCP tool: `store_memory` in `mcp_server/tools.py`
    - Redis fallback queue: `memory_queue:{user_id}` (24h TTL)
    - Performance: <500ms p95 for storage operations
- **Brave Search API**: Web search for internet access tool
- **Stock API**: Portfolio data for stock trader tool
- **Telegram Bot API**: Messaging interface
- **Grok-4 / ChatGPT-5 APIs**: LLM providers for chat generation
  - **Grok-4 Live Search** (Story 4.1 - Implemented):
    - Real-time internet access for time-sensitive queries
    - Auto mode: LLM intelligently decides when to search
    - Cost: $25 per 1,000 sources accessed ($0.025 per source)
    - FREE until November 21, 2025 (promotional period)
    - Projected costs: $56-562/month depending on usage (10-100 users)
    - Logged metrics: search activation, sources accessed, cost per request
    - Monitoring: Use `event="live_search_used"` to filter logs for cost tracking
