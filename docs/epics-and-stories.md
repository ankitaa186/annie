# annie - Epic and Story Breakdown (Refined)

**Author:** Ankit
**Date:** 2025-11-10 (Refined)
**Project Level:** Level 3-4
**Target Scale:** V1.0 MVP

---

## Overview

This document provides the complete epic and story breakdown for annie, decomposing the requirements from the [PRD](./01-product/PRODUCT_REQUIREMENTS.md) into implementable stories with acceptance criteria.

**Epic Summary:**
- **Epic 1:** Foundation & Infrastructure - Project setup, Docker, environment config, logging, MCP server foundation
- **Epic 2:** Core Chat & LLM Integration - Backend API, LLM client, streaming, function calling, error handling
- **Epic 3:** Memory & Persistence - agentic-memories integration for persistent memory
- **Epic 4:** Decision Support Tools - Internet Access and Stock Trader tools
- **Epic 5:** Telegram Bot Interface - Bot setup, message handling, streaming responses
- **Epic 6:** Integration & Quality - Testing, documentation, end-to-end validation

**Total Stories:** 24 stories across 6 epics
**Estimated Duration:** ~10 weeks (50 tasks mapped to stories)

---

## Epic 1: Foundation & Infrastructure

**Goal:** Establish the foundational infrastructure and development environment for Annie, enabling all subsequent development work.

**Scope:** Project structure, Docker setup, environment configuration, logging infrastructure, operational scripts, and MCP server foundation.

**Success Criteria:**
- All Docker services can start successfully
- Environment variables properly configured and validated
- Structured logging works across all services
- MCP server responds to basic tool calls
- Development environment is fully operational
- Operational scripts work correctly

**Dependencies:** None (foundation epic)

---

### Story 1.1: Project Structure & Repository Setup

**As a** developer,  
**I want** a properly structured project repository,  
**So that** I can organize code efficiently and follow best practices.

**Acceptance Criteria:**

**AC #1:** Given a fresh repository, when I check the directory structure, then it includes `backend/`, `mcp_server/`, `telegram_bot/`, `scripts/`, `docs/` directories

**AC #2:** Given the project structure, when I check the repository, then `.gitignore` exists with appropriate exclusions (Python, Docker, IDE files, `.env`, `__pycache__`, `*.pyc`)

**AC #3:** Given the project structure, when I check the repository, then `.dockerignore` exists with appropriate exclusions (`.git`, `docs`, `*.md`, `.env`)

**AC #4:** Given the repository, when I check Python structure, then virtual environment directories are excluded and `requirements.txt` structure is defined

**AC #5:** Given the repository, when I check documentation, then initial `README.md` exists with project overview and setup instructions

**Prerequisites:** None (first story)

**Technical Notes:**
- Maps to Tasks: 1.1 (partial)
- Creates foundation for all subsequent stories
- Ensures clean repository structure

**Estimated Effort:** 2 points (1 day)

---

### Story 1.2: Docker Compose & Service Configuration

**As a** developer,  
**I want** Docker Compose configuration with all services,  
**So that** I can run all Annie services together with proper networking.

**Acceptance Criteria:**

**AC #1:** Given Docker is installed, when I check `docker-compose.yml`, then it defines all services (Backend API, MCP Server, Telegram Bot, Redis)

**AC #2:** Given Docker Compose, when I check service configuration, then each service has proper network configuration and dependencies defined

**AC #3:** Given Docker Compose, when I run `docker-compose up`, then all services start successfully without errors

**AC #4:** Given Docker Compose, when I check health checks, then each service has health check configuration that validates service readiness

**AC #5:** Given Docker Compose, when I check volume mounts, then development volumes are configured for hot-reload capability

**AC #6:** Given Docker Compose, when I check service health, then all services pass their health checks within 30 seconds of startup

**Prerequisites:** Story 1.1

**Technical Notes:**
- Maps to Tasks: 1.2, 1.3, 1.4, 1.5
- Establishes containerized development environment
- Enables parallel service development

**Estimated Effort:** 3 points (3 days)

---

### Story 1.3: Environment Configuration & Secrets Management

**As a** developer,  
**I want** environment configuration and secrets management,  
**So that** I can securely configure Annie without hardcoding sensitive data.

**Acceptance Criteria:**

**AC #1:** Given the project, when I check `env.example`, then it includes all required environment variables with descriptions:
  - LLM API keys (Grok-4, ChatGPT-5)
  - Telegram bot token
  - Brave Search API key
  - Stock API key
  - agentic-memories service URL
  - Redis configuration
  - Service ports and URLs

**AC #2:** Given environment setup, when I run `./run_docker.sh`, then it interactively creates `.env` file from `env.example` if missing

**AC #3:** Given environment variables, when services start, then all required variables are validated and missing variables cause clear error messages

**AC #4:** Given environment variables, when I check security, then sensitive values (API keys, tokens) are never logged or exposed in error messages

**AC #5:** Given environment configuration, when services start, then environment-specific values (dev/staging/prod) can be configured via `.env` file

**AC #6:** Given the `.env` file, when I check `.gitignore`, then `.env` is excluded from version control

**Prerequisites:** Story 1.1

**Technical Notes:**
- Maps to Tasks: 1.6 (partial)
- Critical for security and configuration management
- Enables different deployment environments

**Estimated Effort:** 2 points (1.5 days)

---

### Story 1.4: Logging Infrastructure

**As a** developer,  
**I want** structured logging across all services,  
**So that** I can debug issues and monitor Annie's behavior effectively.

**Acceptance Criteria:**

**AC #1:** Given any service, when it starts, then structured logging is configured with JSON format (for production) and human-readable format (for development)

**AC #2:** Given logging, when I check log output, then logs include timestamp, service name, log level, message, and context (user_id, conversation_id, request_id)

**AC #3:** Given logging, when errors occur, then error logs include stack traces, error codes, and relevant context for debugging

**AC #4:** Given logging, when I check log levels, then services support configurable log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL) via environment variable

**AC #5:** Given logging, when I check Docker logs, then logs from all services are visible via `docker-compose logs` with service filtering

**AC #6:** Given logging, when sensitive data is logged, then API keys, tokens, and user personal data are masked/redacted in logs

**AC #7:** Given logging, when performance issues occur, then slow operations (>1s) are logged with timing information

**Prerequisites:** Story 1.2

**Technical Notes:**
- Maps to Tasks: 1.7 (partial), 2.1 (partial)
- Critical for debugging and monitoring
- Enables production observability

**Estimated Effort:** 2 points (1.5 days)

---

### Story 1.5: Operational Scripts & Makefile

**As a** developer,  
**I want** operational scripts and Makefile commands,  
**So that** I can easily manage Annie's development lifecycle.

**Acceptance Criteria:**

**AC #1:** Given the project, when I check `run_docker.sh`, then it:
  - Checks Docker installation and version
  - Validates Docker Compose is available
  - Creates `.env` interactively if missing
  - Verifies required dependencies
  - Starts all services via Docker Compose

**AC #2:** Given the Makefile, when I run `make start`, then all services start successfully

**AC #3:** Given the Makefile, when I run `make stop`, then all services stop gracefully

**AC #4:** Given the Makefile, when I run `make logs`, then logs from all services are displayed with service names

**AC #5:** Given the Makefile, when I run `make logs SERVICE=backend`, then logs from only the backend service are displayed

**AC #6:** Given the Makefile, when I run `make test`, then test suite runs for all services

**AC #7:** Given the Makefile, when I run `make clean`, then Docker containers, volumes, and temporary files are cleaned up

**AC #8:** Given the scripts, when I check execution, then scripts have proper error handling and informative error messages

**Prerequisites:** Story 1.2, Story 1.3

**Technical Notes:**
- Maps to Tasks: 1.6 (partial)
- Improves developer experience
- Standardizes common operations

**Estimated Effort:** 2 points (1.5 days)

---

### Story 1.6: MCP Server Foundation

**As a** developer,  
**I want** a working MCP server with basic tool support,  
**So that** I can call MCP tools from the backend.

**Acceptance Criteria:**

**AC #1:** Given the MCP server Dockerfile, when I build the image, then it includes MCP Python SDK (`pip install mcp`) and all tool dependencies

**AC #2:** Given the MCP server, when it starts, then it initializes stdio transport and listens for JSON-RPC 2.0 messages

**AC #3:** Given the MCP server is running, when I call the health check tool via Docker exec, then it responds with `{"status": "ok", "timestamp": "..."}`

**AC #4:** Given the MCP server, when I execute a tool call via Docker exec pattern (`docker exec mcp_server echo '{"jsonrpc":"2.0","method":"tools/call",...}'`), then the tool executes and returns results via stdio

**AC #5:** Given the MCP server, when I check logs, then structured logging is visible with tool call information (tool name, parameters, execution time, results)

**AC #6:** Given the MCP server, when an invalid tool call is made, then it returns a proper JSON-RPC error response with error code and message

**Prerequisites:** Story 1.2, Story 1.4

**Technical Notes:**
- Maps to Task: 1.7
- Establishes MCP communication pattern
- Enables tool development in Epic 4

**Estimated Effort:** 3 points (2 days)

---

## Epic 2: Core Chat & LLM Integration

**Goal:** Implement the core backend API with LLM integration, streaming support, function calling capabilities, and robust error handling.

**Scope:** FastAPI backend, LLM client (Grok-4/ChatGPT-5), SSE streaming, function calling, MCP client, Redis state management, error handling patterns.

**Success Criteria:**
- Backend API responds to requests
- LLM streaming works end-to-end
- Function calling enables tool invocation
- State management persists conversations
- Error handling provides graceful degradation
- Performance meets requirements (<500ms first token, <2s p95 response)

**Dependencies:** Epic 1

---

### Story 2.1: Backend API Foundation

**As a** developer,  
**I want** a FastAPI backend with health checks and basic routing,  
**So that** I can build API endpoints for Annie.

**Acceptance Criteria:**

**AC #1:** Given the backend service, when I start it, then FastAPI application initializes successfully with proper middleware (CORS, request logging)

**AC #2:** Given the backend API, when I call `GET /health`, then it returns `{"status": "ok", "timestamp": "2025-11-10T12:00:00Z"}` with 200 status code

**AC #3:** Given the backend API, when I call `GET /health/detailed`, then it returns component health status:
  ```json
  {
    "status": "ok",
    "components": {
      "mcp_server": "ok",
      "redis": "ok",
      "llm_api": "ok",
      "agentic_memories": "ok"
    },
    "timestamp": "..."
  }
  ```

**AC #4:** Given the backend API, when I check Docker health checks, then the service passes health validation (`docker inspect` shows healthy status)

**AC #5:** Given the backend API, when a component is down (e.g., Redis), then `/health/detailed` reflects the component status without failing the entire health check

**AC #6:** Given the backend API, when I check request logging, then all requests are logged with method, path, status code, and response time

**Prerequisites:** Story 1.2, Story 1.4

**Technical Notes:**
- Maps to Tasks: 2.1, 2.2
- Establishes API foundation
- Enables subsequent API development

**Estimated Effort:** 2 points (1.5 days)

---

### Story 2.2: LLM Client Setup & Provider Management

**As a** developer,  
**I want** a unified LLM client with provider selection and fallback,  
**So that** Annie can use multiple LLM providers reliably.

**Acceptance Criteria:**

**AC #1:** Given Grok-4 API key is configured, when I initialize the LLM client, then it authenticates and can make API calls successfully

**AC #2:** Given the LLM client, when I configure providers, then it supports Grok-4 (primary) and ChatGPT-5 (fallback) with provider selection logic

**AC #3:** Given Grok-4 fails (network error, API error, rate limit), when I call the LLM client, then it automatically falls back to ChatGPT-5 within 2 seconds

**AC #4:** Given both LLMs fail, when I call the LLM client, then it returns a clear, user-friendly error message: "I'm experiencing technical difficulties. Please try again in a moment."

**AC #5:** Given the LLM client, when I check error handling, then provider failures are logged with error details, retry attempts, and fallback actions

**AC #6:** Given the LLM client, when rate limiting occurs, then it handles rate limit errors gracefully and suggests retry after appropriate delay

**AC #7:** Given the LLM client, when I check configuration, then API keys, base URLs, and timeouts are configurable via environment variables

**Prerequisites:** Story 2.1

**Technical Notes:**
- Maps to Tasks: 2.3, 2.4, 2.5
- Core functionality for Annie's responses
- Enables reliable LLM access

**Estimated Effort:** 3 points (2.5 days)

---

### Story 2.3: SSE Streaming Support

**As a** user,  
**I want** Annie to respond with streaming text,  
**So that** I see responses in real-time without waiting for complete generation.

**Acceptance Criteria:**

**AC #1:** Given a chat request, when I call the LLM client with streaming enabled, then it streams tokens via SSE format (`data: {"type":"token","content":"..."}\n\n`)

**AC #2:** Given a streaming request, when I call `GET /api/stream/{conversation_id}`, then tokens stream continuously until completion with proper SSE event formatting

**AC #3:** Given streaming, when the first token arrives, then it arrives within 500ms (p95) of request initiation

**AC #4:** Given streaming completes, when I check the response, then it includes completion event: `{"type":"done","tokens_used":{"prompt":100,"completion":200}}`

**AC #5:** Given streaming, when a client disconnects, then the stream is properly closed and resources are cleaned up

**AC #6:** Given streaming, when an error occurs during streaming, then an error event is sent: `{"type":"error","message":"..."}` and the stream closes gracefully

**AC #7:** Given streaming, when I check connection management, then multiple concurrent streams are supported (up to 100 concurrent connections)

**Prerequisites:** Story 2.2

**Technical Notes:**
- Maps to Task: 2.6
- Core user experience feature
- Enables real-time interaction

**Estimated Effort:** 3 points (2.5 days)

---

### Story 2.4: Function Calling for MCP Tools

**As a** user,  
**I want** Annie to use tools (internet search, memories, stock analysis) when needed,  
**So that** I get informed, personalized responses.

**Acceptance Criteria:**

**AC #1:** Given the LLM client, when I send a message requiring internet search ("What's the weather today?"), then the LLM requests the `internet_search` tool via function calling with proper schema

**AC #2:** Given a function call request, when the backend receives it, then it calls the MCP server tool via Docker exec with proper JSON-RPC 2.0 formatting

**AC #3:** Given a tool call, when the tool executes, then results are returned within 5 seconds (p95) and added to LLM context

**AC #4:** Given tool results, when the LLM generates final response, then it incorporates tool results into the answer with proper attribution

**AC #5:** Given multiple tool calls in sequence, when Annie needs multiple tools (e.g., search + memory retrieval), then tools are called in correct order and results combined appropriately

**AC #6:** Given a tool call fails, when the tool returns an error, then the error is handled gracefully and Annie informs the user without crashing

**AC #7:** Given function calling, when I check tool schemas, then all available tools are registered with proper descriptions, parameters, and return types

**Prerequisites:** Story 2.2, Story 1.6

**Technical Notes:**
- Maps to Tasks: 2.7, 2.8
- Enables tool integration
- Requires MCP server foundation (Epic 1)

**Estimated Effort:** 3 points (2 days)

---

### Story 2.5: Conversation State Management

**As a** user,  
**I want** Annie to remember our conversation context,  
**So that** I don't have to repeat information.

**Acceptance Criteria:**

**AC #1:** Given a user sends a message, when the backend processes it, then a session is created in Redis with structure:
  ```json
  {
    "user_id": "12345",
    "platform": "telegram",
    "conversation_id": "conv_abc123",
    "created_at": "2025-11-10T12:00:00Z",
    "last_activity": "2025-11-10T12:00:00Z"
  }
  ```

**AC #2:** Given an active session, when the user sends another message, then the conversation history is retrieved from Redis with all previous messages

**AC #3:** Given conversation history, when the LLM generates a response, then it uses the full conversation context (up to last 20 messages or 4000 tokens, whichever is smaller)

**AC #4:** Given a session is inactive for 1 hour, when I check Redis, then the session has expired (TTL enforced) and a new session is created on next message

**AC #5:** Given conversation state, when I call `GET /api/conversations/{user_id}`, then it returns conversation history with pagination support (max 50 messages per page)

**AC #6:** Given Redis connection fails, when a message is processed, then the system continues without conversation context but logs the error

**AC #7:** Given conversation state, when I check performance, then conversation retrieval completes within 50ms (p95)

**Prerequisites:** Story 2.1

**Technical Notes:**
- Maps to Tasks: 2.9, 2.10, 2.11
- Enables context-aware conversations
- Foundation for memory integration (Epic 3)

**Estimated Effort:** 3 points (3 days)

---

### Story 2.6: Error Handling Patterns

**As a** developer/user,  
**I want** robust error handling across the backend,  
**So that** Annie gracefully handles failures and provides helpful feedback.

**Acceptance Criteria:**

**AC #1:** Given any API endpoint, when an unhandled exception occurs, then it returns a user-friendly error response:
  ```json
  {
    "error": {
      "code": "INTERNAL_ERROR",
      "message": "Something went wrong. Please try again.",
      "request_id": "req_abc123"
    }
  }
  ```
  with 500 status code

**AC #2:** Given external service failures, when agentic-memories is down, then the system continues without memory context and logs the failure without crashing

**AC #3:** Given external service failures, when MCP server is unavailable, then tool calls fail gracefully with clear error messages to users

**AC #4:** Given rate limiting, when LLM API rate limits are hit, then the system queues requests or returns appropriate rate limit error with retry-after header

**AC #5:** Given validation errors, when invalid input is provided, then the API returns 400 status with specific validation error details

**AC #6:** Given timeout scenarios, when a request takes >30 seconds, then it times out gracefully with appropriate error message

**AC #7:** Given error handling, when I check error logs, then all errors include request context (user_id, conversation_id, request_id) for debugging

**Prerequisites:** Story 2.1, Story 2.2

**Technical Notes:**
- Maps to error handling across Tasks: 2.3-2.11
- Critical for production reliability
- Ensures graceful degradation

**Estimated Effort:** 2 points (1.5 days)

---

### Story 2.7: Move Timeout Configuration to Environment Variables (Technical Debt)

**As a** developer/operator,
**I want** timeout values configurable via environment variables instead of hardcoded,
**So that** I can adjust timeouts for different environments without code changes.

**Acceptance Criteria:**

**AC #1:** Given `env.example`, when I check timeout configuration, then it includes environment variables:
  - `LLM_REQUEST_TIMEOUT` (default: 180)
  - `LLM_FAILOVER_TIMEOUT` (default: 180)
  - `LLM_STREAMING_TIMEOUT` (default: 180)
  - `BACKEND_CONNECT_TIMEOUT` (default: 10)
  - `BACKEND_SOCK_READ_TIMEOUT` (default: 180)
  - `TELEGRAM_FIRST_TOKEN_TIMEOUT` (default: 120)

**AC #2:** Given `backend/api/llm_client.py`, when I check the LLMClient class, then hardcoded timeout class variables are replaced with instance variables loaded from environment config with sensible defaults

**AC #3:** Given `telegram_bot/backend_client.py`, when I check the BackendClient class, then hardcoded timeout values are replaced with environment variable loading with fallback defaults

**AC #4:** Given environment variables are not set, when services start, then they use documented default values without errors

**AC #5:** Given timeout environment variables are set, when I restart services, then new timeout values are applied and logged at startup

**AC #6:** Given timeout configuration changes, when I update `.env` file and restart, then no code changes are required to adjust timeout behavior

**AC #7:** Given the implementation, when I check logging, then timeout values are logged at service initialization showing which values are being used (env vs defaults)

**Prerequisites:** Story 2.2, Story 2.3

**Technical Notes:**
- Technical debt - improves operational flexibility
- Affected files:
  - `env.example` - add new timeout variables
  - `backend/api/llm_client.py` - convert class vars to instance vars loaded from config
  - `telegram_bot/backend_client.py` - load timeouts from environment
- No behavioral changes - just configuration externalization
- Enables different timeout tuning for dev/staging/prod
- Backward compatible via sensible defaults

**Estimated Effort:** 2 points (1 day)

---

## Epic 3: Memory & Persistence

**Goal:** Integrate agentic-memories service to enable persistent memory of past decisions, outcomes, and user preferences.

**Scope:** agentic-memories API client, memory storage, memory retrieval, portfolio summary integration.

**Success Criteria:**
- Memories are stored after conversations
- Relevant memories are retrieved for decision support
- Graceful degradation when service unavailable
- Memory retrieval performance <300ms (p95)

**Dependencies:** Epic 1, Epic 2

---

### Story 3.1: Memory Storage Integration

**As a** user,  
**I want** Annie to remember our conversations and decisions,  
**So that** future advice is personalized based on my history.

**Acceptance Criteria:**

**AC #1:** Given agentic-memories service is available, when a conversation ends (user sends "thanks" or conversation times out), then conversation context is stored via `store_memory` tool with:
  - user_id
  - conversation summary
  - key decisions made
  - user preferences expressed
  - timestamp

**AC #2:** Given memory storage, when I check agentic-memories, then the conversation is stored with proper structure and can be retrieved later

**AC #3:** Given agentic-memories service is down, when a conversation ends, then the system continues without error, logs the failure, and stores memory in Redis temporarily for retry

**AC #4:** Given memory storage fails, when I send another message, then Annie continues working without memory context but informs the user: "Note: I'm having trouble accessing your memory right now, but I can still help."

**AC #5:** Given memory is stored, when I check the stored data, then it includes:
  - Decision context (what decision was made, options considered)
  - User preferences (risk tolerance, priorities)
  - Conversation flow (key topics discussed)
  - Outcomes (if user provides feedback)

**AC #6:** Given memory storage, when I check performance, then memory storage completes within 500ms (p95)

**Prerequisites:** Story 2.4, Story 1.6

**Technical Notes:**
- Maps to Tasks: 3.4, 3.5, 3.7
- Enables persistent memory
- Critical for personalized advice

**Estimated Effort:** 3 points (2.5 days)

---

### Story 3.2: Memory Retrieval for Decision Support

**As a** user,  
**I want** Annie to use my past decisions when giving advice,  
**So that** recommendations are personalized and relevant.

**Acceptance Criteria:**

**AC #1:** Given a user asks for decision help ("Should I invest in stocks?"), when Annie processes the request, then it retrieves relevant memories via `retrieve_memories` tool with query based on decision context

**AC #2:** Given retrieved memories, when Annie analyzes options, then it uses memory context in pros/cons analysis, referencing past decisions: "Based on your previous preference for conservative investments..."

**AC #3:** Given memory retrieval, when Annie provides recommendations, then it references past decisions and outcomes: "Last time you chose X, and it worked well because..."

**AC #4:** Given no relevant memories exist, when Annie provides advice, then it works without memory context but acknowledges: "I don't have your past decision history yet, but here's my analysis..."

**AC #5:** Given memory retrieval takes >300ms, when I check performance, then it's logged as a performance issue and optimization is considered

**AC #6:** Given persona-aware retrieval, when memories are retrieved, then they're filtered by decision-making persona (e.g., "Stock Trader" persona retrieves financial decision memories)

**AC #7:** Given memory retrieval, when I check relevance, then retrieved memories are ranked by relevance and top 5 most relevant memories are used

**Prerequisites:** Story 3.1

**Technical Notes:**
- Maps to Tasks: 3.6, 3.7
- Enables personalized recommendations
- Core to decision support value proposition

**Estimated Effort:** 2 points (1.5 days)

---

## Epic 4: Decision Support Tools

**Goal:** Implement MCP tools that enable Annie to provide informed decision support through internet access and stock market analysis.

**Scope:** Internet Access tool (Brave Search), Stock Trader tool (market analysis, recommendations).

**Success Criteria:**
- Internet search provides real-time information
- Stock analysis provides actionable insights
- Tools integrate seamlessly with LLM function calling
- Tool execution <5s (p95)

**Dependencies:** Epic 1, Epic 2

---

### Story 4.1: Internet Access Tool

**As a** user,  
**I want** Annie to access real-time information from the internet,  
**So that** my decisions are informed by current data.

**Acceptance Criteria:**

**AC #1:** Given a user asks for current information ("What's happening with Tesla stock?"), when Annie needs internet search, then it calls the `internet_search` tool with properly formatted query

**AC #2:** Given a search query, when the tool executes, then it calls Brave Search API and returns relevant results within 2 seconds (p95)

**AC #3:** Given search results, when Annie responds, then it incorporates current information into the answer with source attribution: "According to recent news..."

**AC #4:** Given rate limiting, when search requests exceed limits (e.g., 100 requests/hour), then the tool handles rate limit errors gracefully and suggests retry after delay

**AC #5:** Given Brave Search API fails, when the tool is called, then it returns an error and Annie continues without real-time data, informing the user: "I couldn't access current information, but here's what I know..."

**AC #6:** Given search results, when I check the response format, then results include:
  - Title (max 100 chars)
  - URL
  - Snippet (max 200 chars)
  - Relevance score
  - Up to 10 results per query

**AC #7:** Given search queries, when I check query optimization, then queries are optimized for relevance (removed stop words, added context)

**Prerequisites:** Story 2.4, Story 1.6

**Technical Notes:**
- Maps to Tasks: 3.1, 3.2, 3.3
- Enables real-time intelligence
- Critical for decision support

**Estimated Effort:** 2 points (2 days)

---

### Story 4.2: Stock Trader Tool - Market Analysis

**As a** user,  
**I want** Annie to analyze stock markets and provide insights,  
**So that** I can make informed investment decisions.

**Acceptance Criteria:**

**AC #1:** Given a user asks about a stock ("Analyze AAPL"), when Annie needs market analysis, then it calls the `analyze_stock` tool with stock symbol

**AC #2:** Given a stock symbol, when the tool executes, then it retrieves real-time price and historical data from stock API (Alpha Vantage/Polygon.io/Finnhub) within 3 seconds (p95)

**AC #3:** Given stock data, when analysis is performed, then it includes:
  - Current price and 52-week range
  - Technical indicators (RSI, MACD, Moving Averages)
  - Trend analysis (bullish/bearish/neutral)
  - Volume analysis (above/below average)
  - Price change (1d, 1w, 1m, 1y)

**AC #4:** Given analysis results, when Annie responds, then it provides clear market insights with reasoning: "AAPL is currently bullish based on RSI of 65 and upward trend..."

**AC #5:** Given stock API fails, when the tool is called, then it falls back to internet search for stock information and informs the user of the limitation

**AC #6:** Given analysis, when I check the response, then it includes risk assessment (low/medium/high) and market context (sector performance, market conditions)

**AC #7:** Given invalid stock symbols, when the tool is called, then it returns a clear error message: "Stock symbol 'INVALID' not found. Please check the symbol and try again."

**Prerequisites:** Story 2.4, Story 1.6

**Technical Notes:**
- Maps to Tasks: 3.8, 3.9, 3.11
- Enables financial decision support
- Core to prosperity value proposition

**Estimated Effort:** 4 points (3.5 days)

---

### Story 4.3: Stock Trader Tool - Personalized Recommendations

**As a** user,  
**I want** Annie to provide personalized stock recommendations based on my risk profile,  
**So that** investment advice matches my preferences.

**Acceptance Criteria:**

**AC #1:** Given a user asks for stock recommendations ("Should I buy AAPL?"), when Annie provides advice, then it calls the `recommend_stock` tool with stock symbol and user context

**AC #2:** Given stock analysis, when recommendations are generated, then they include:
  - Buy/hold/sell recommendation
  - Confidence level (high/medium/low)
  - Reasoning (3-5 key points)
  - Risk assessment
  - Time horizon suggestion

**AC #3:** Given user's risk profile from memories, when recommendations are made, then they align with user's risk tolerance (conservative/moderate/aggressive)

**AC #4:** Given recommendations, when Annie responds, then it explains the reasoning: "Based on your conservative risk profile and AAPL's current volatility, I recommend a HOLD position because..."

**AC #5:** Given portfolio summary from memories, when recommendations are made, then they consider existing portfolio holdings: "You already have 20% tech exposure, so consider diversifying..."

**AC #6:** Given recommendations, when I check personalization, then recommendations reference past investment decisions: "You previously preferred dividend stocks, so consider..."

**Prerequisites:** Story 4.2, Story 3.2

**Technical Notes:**
- Maps to Tasks: 3.10, 3.11
- Combines stock analysis with memory context
- Enables personalized financial advice

**Estimated Effort:** 2 points (1.5 days)

---

## Epic 5: Telegram Bot Interface

**Goal:** Implement the Telegram bot interface that enables users to chat with Annie via Telegram with streaming responses.

**Scope:** Telegram bot setup, message handling, backend integration, streaming responses, error handling.

**Success Criteria:**
- Users can send messages via Telegram
- Bot responds with streaming text
- Messages are properly formatted
- Error handling is user-friendly
- Bot handles 100+ concurrent users

**Dependencies:** Epic 2

---

### Story 5.1: Telegram Bot Setup & Message Reception

**As a** user,  
**I want** to chat with Annie via Telegram,  
**So that** I can get decision support on my mobile device.

**Acceptance Criteria:**

**AC #1:** Given Telegram bot token is configured, when the bot service starts, then it connects to Telegram API successfully and starts polling for updates

**AC #2:** Given the bot is running, when I send a message via Telegram, then the bot receives the message within 1 second

**AC #3:** Given a message is received, when I check logs, then user_id and message text are extracted correctly:
  - user_id: Telegram user ID (numeric)
  - message_text: Full message content
  - timestamp: Message timestamp
  - message_id: Telegram message ID

**AC #4:** Given different message types, when I send text messages, then the bot handles them correctly

**AC #5:** Given different message types, when I send voice messages, then the bot handles them appropriately (for V1, may return "Voice messages coming soon" or transcribe)

**AC #6:** Given the bot receives a message, when I check processing, then it forwards the message to backend API (`POST /api/chat`) with proper formatting

**AC #7:** Given the bot, when I check error handling, then connection failures are handled gracefully with retry logic and logging

**Prerequisites:** Story 2.1, Story 1.2

**Technical Notes:**
- Maps to Tasks: 4.1, 4.2
- Establishes Telegram interface
- Enables user interaction

**Estimated Effort:** 2 points (2 days)

---

### Story 5.2: Streaming Response Delivery

**As a** user,  
**I want** to see Annie's responses stream in real-time,  
**So that** I don't wait for complete responses.

**Acceptance Criteria:**

**AC #1:** Given a user sends a message, when Annie responds, then responses stream incrementally to Telegram (tokens appear as they're generated)

**AC #2:** Given streaming responses, when I receive messages, then I see tokens appearing in real-time (not all at once), with updates every 100-500ms

**AC #3:** Given a long response (>4096 chars), when Annie responds, then messages are split appropriately for Telegram (max 4096 chars per message) with proper message continuation

**AC #4:** Given streaming, when Annie is typing, then a typing indicator is shown in Telegram (`send_chat_action(chat_id, "typing")`)

**AC #5:** Given streaming completes, when I check the conversation, then the complete response is visible as a single coherent message (or properly split messages)

**AC #6:** Given streaming fails, when an error occurs, then the user receives a clear error message: "I encountered an issue generating a response. Please try again."

**AC #7:** Given streaming, when I check performance, then first message appears within 2 seconds of user sending message (including LLM first token latency)

**Prerequisites:** Story 5.1, Story 2.3

**Technical Notes:**
- Maps to Tasks: 4.3, 4.4
- Core user experience feature
- Requires backend streaming (Story 2.3)

**Estimated Effort:** 3 points (3 days)

---

### Story 5.3: Message Formatting & Error Handling

**As a** user,  
**I want** clearly formatted messages and helpful error messages,  
**So that** I understand Annie's responses and know what to do if something goes wrong.

**Acceptance Criteria:**

**AC #1:** Given Annie responds, when messages are sent, then markdown formatting is properly rendered in Telegram:
  - **Bold** text renders correctly
  - *Italic* text renders correctly
  - `Code` blocks render correctly
  - Links render as clickable

**AC #2:** Given tool results (stock data, search results), when Annie responds, then results are formatted clearly with structure:
  - Stock data: Tables or structured text
  - Search results: Numbered list with titles and URLs
  - Memory references: Clear attribution

**AC #3:** Given an error occurs, when the backend fails, then the user receives a user-friendly error message: "I'm having trouble right now. Please try again in a moment." (not technical error details)

**AC #4:** Given service failures, when agentic-memories is down, then the user is informed: "Note: I'm having trouble accessing your memory, but I can still help." and conversation continues

**AC #5:** Given retry scenarios, when a transient error occurs (network timeout, rate limit), then the bot suggests retrying: "Please try again in a few seconds."

**AC #6:** Given error messages, when I check the format, then they're clear, actionable, and not technical jargon

**AC #7:** Given message formatting, when I check edge cases, then:
  - Empty responses are handled gracefully
  - Very long responses are split properly
  - Special characters are escaped correctly
  - Emojis render properly

**Prerequisites:** Story 5.2

**Technical Notes:**
- Maps to Tasks: 4.5, 4.6
- Improves user experience
- Critical for trust building

**Estimated Effort:** 2 points (2 days)

---

## Epic 6: Integration & Quality

**Goal:** Ensure all components work together seamlessly, meet quality standards, and are ready for deployment.

**Scope:** End-to-end integration, testing (unit, integration, E2E), error scenario testing, performance testing, documentation.

**Success Criteria:**
- All components integrated successfully
- Test coverage meets targets (80%+)
- Performance requirements met
- Documentation complete
- System ready for production deployment

**Dependencies:** Epics 1-5

---

### Story 6.1: End-to-End Integration

**As a** developer,  
**I want** all components integrated and working together,  
**So that** Annie functions as a complete system.

**Acceptance Criteria:**

**AC #1:** Given all services are running, when a user sends a message via Telegram, then the complete flow works:
  Telegram → Backend → LLM → Tools → Response → Telegram
  with all components functioning correctly

**AC #2:** Given tool calling, when Annie needs internet search, then the flow works:
  LLM function call → MCP client → MCP server → Tool → Results → LLM → Response
  with proper error handling at each step

**AC #3:** Given memory integration, when Annie responds, then memories are:
  - Retrieved before generating response (if relevant)
  - Used in LLM context
  - Stored after conversation ends
  All within the same request flow

**AC #4:** Given multiple tools, when Annie needs multiple tools in one conversation (e.g., search + stock analysis + memory), then tools are called correctly in sequence and results combined appropriately

**AC #5:** Given streaming, when Annie responds, then streaming works end-to-end:
  LLM streams → Backend SSE → Telegram bot → User sees incremental updates
  with proper connection management

**AC #6:** Given integration, when I check error scenarios, then failures at any step are handled gracefully without breaking the entire flow

**Prerequisites:** Epics 1-5 complete

**Technical Notes:**
- Maps to Tasks: 5.1, 5.2
- Validates complete system
- Identifies integration issues

**Estimated Effort:** 3 points (3 days)

---

### Story 6.2: Unit & Integration Testing

**As a** developer,  
**I want** comprehensive unit and integration test coverage,  
**So that** I'm confident in Annie's reliability and quality.

**Acceptance Criteria:**

**AC #1:** Given unit tests, when I run the test suite (`make test`), then backend components have 80%+ code coverage (LLM client, MCP client, state manager, API routes)

**AC #2:** Given unit tests, when I run the test suite, then MCP tools have 80%+ code coverage (internet access, memories, stock trader tools)

**AC #3:** Given unit tests, when I check test quality, then tests include:
  - Happy path scenarios
  - Error scenarios
  - Edge cases
  - Boundary conditions

**AC #4:** Given integration tests, when I run integration tests, then backend + MCP integration works correctly:
  - MCP client can call tools
  - Tool results are properly formatted
  - Error handling works end-to-end

**AC #5:** Given integration tests, when I run integration tests, then Telegram + Backend integration works correctly:
  - Messages are forwarded correctly
  - Streaming responses work
  - Error handling is proper

**AC #6:** Given tests, when I check test execution, then tests run in CI/CD pipeline and fail builds on test failures

**AC #7:** Given tests, when I check test performance, then test suite completes within 5 minutes

**Prerequisites:** Story 6.1

**Technical Notes:**
- Maps to Tasks: 5.3, 5.4, 5.5
- Ensures quality and reliability
- Validates component integration

**Estimated Effort:** 4 points (5 days)

---

### Story 6.3: Error Scenario & Performance Testing

**As a** developer,  
**I want** comprehensive error scenario and performance testing,  
**So that** Annie handles failures gracefully and meets performance requirements.

**Acceptance Criteria:**

**AC #1:** Given error scenario tests, when I test failure cases, then graceful degradation works for all error scenarios:
  - agentic-memories down → Continues without memory
  - LLM API failure → Falls back to alternative provider
  - Internet search failure → Continues without real-time data
  - Stock API failure → Falls back to internet search
  - MCP server crash → Returns error to user gracefully
  - Redis connection failure → Continues without conversation context

**AC #2:** Given error scenario tests, when I test timeout scenarios, then requests timeout gracefully after 30 seconds with appropriate error messages

**AC #3:** Given performance tests, when I test first token latency, then it's <500ms (p95) for 95% of requests

**AC #4:** Given performance tests, when I test tool call completion, then tool calls complete within 5 seconds (p95) for 95% of requests

**AC #5:** Given performance tests, when I test memory retrieval speed, then memory retrieval completes within 300ms (p95) for 95% of requests

**AC #6:** Given performance tests, when I test concurrent users, then the system handles 100 concurrent users without degradation (response time <2s p95)

**AC #7:** Given performance tests, when I test load, then the system handles 1000 requests/minute without errors

**AC #8:** Given performance tests, when I check bottlenecks, then performance bottlenecks are identified and documented for optimization

**Prerequisites:** Story 6.2

**Technical Notes:**
- Maps to Tasks: 5.6, 5.7
- Validates performance requirements
- Ensures production readiness

**Estimated Effort:** 3 points (3 days)

---

### Story 6.4: Documentation & Deployment Readiness

**As a** developer/user,  
**I want** complete documentation,  
**So that** I can set up, use, and maintain Annie.

**Acceptance Criteria:**

**AC #1:** Given API documentation, when I check the docs, then all endpoints are documented with:
  - Request/response examples
  - Parameter descriptions
  - Error codes and meanings
  - Authentication requirements

**AC #2:** Given setup guide, when I follow the guide, then I can set up Annie from scratch successfully:
  - Clone repository
  - Configure environment variables
  - Start services via Docker Compose
  - Verify all services are running

**AC #3:** Given troubleshooting guide, when I encounter common issues, then solutions are documented:
  - Service won't start
  - API connection errors
  - Tool execution failures
  - Performance issues

**AC #4:** Given the system, when I check deployment readiness, then all services can be deployed via Docker Compose with:
  - Production-ready configuration
  - Health checks enabled
  - Logging configured
  - Error handling in place

**AC #5:** Given documentation, when I review it, then it's clear, complete, and up-to-date with:
  - Architecture diagrams
  - Data flow diagrams
  - API reference
  - Configuration guide

**AC #6:** Given documentation, when I check examples, then code examples are provided for:
  - API usage
  - Tool development
  - Error handling
  - Testing

**Prerequisites:** Story 6.3

**Technical Notes:**
- Maps to Tasks: 5.8, 5.9, 5.10
- Enables deployment and maintenance
- Critical for project success

**Estimated Effort:** 3 points (3 days)

---

## Traceability Matrix

### PRD Requirements → Epics → Stories → Tasks

| PRD Requirement | Epic | Story | Implementation Tasks | Status |
|----------------|------|-------|---------------------|--------|
| Chat with Annie via Telegram | Epic 5 | Story 5.1, 5.2 | Tasks 4.1-4.6 | ⏳ Pending |
| Streaming responses | Epic 2, Epic 5 | Story 2.3, Story 5.2 | Tasks 2.6, 4.4 | ⏳ Pending |
| AI-powered recommendations | Epic 2 | Story 2.2, Story 2.4 | Tasks 2.3-2.7 | ⏳ Pending |
| Real-time information access | Epic 4 | Story 4.1 | Tasks 3.1-3.3 | ⏳ Pending |
| Remember past decisions | Epic 3 | Story 3.1, Story 3.2 | Tasks 3.4-3.7 | ⏳ Pending |
| Stock trading advisor | Epic 4 | Story 4.2, Story 4.3 | Tasks 3.8-3.11 | ⏳ Pending |
| Pros/cons analysis | Epic 2, Epic 3 | Story 2.2, Story 3.2 | Embedded in LLM + Memory | ⏳ Pending |
| Personalized advice | Epic 3 | Story 3.2 | Tasks 3.6, 3.7 | ⏳ Pending |
| MCP protocol integration | Epic 1, Epic 2 | Story 1.6, Story 2.4 | Tasks 1.7, 2.8 | ⏳ Pending |
| Docker deployment | Epic 1 | Story 1.1, Story 1.2 | Tasks 1.1-1.6 | ⏳ Pending |
| Environment configuration | Epic 1 | Story 1.3 | Task 1.6 (partial) | ⏳ Pending |
| Logging & monitoring | Epic 1 | Story 1.4 | Tasks 1.7, 2.1 (partial) | ⏳ Pending |
| Error handling | Epic 2 | Story 2.6 | Embedded across Tasks 2.3-2.11 | ⏳ Pending |

---

## Story Sequencing & Dependencies

### Phase 1: Foundation (Week 1-2)
1. Story 1.1: Project Structure & Repository Setup
2. Story 1.2: Docker Compose & Service Configuration (requires Story 1.1)
3. Story 1.3: Environment Configuration & Secrets Management (requires Story 1.1) - **Can run in parallel with 1.2**
4. Story 1.4: Logging Infrastructure (requires Story 1.2) - **Can run in parallel with 1.3**
5. Story 1.5: Operational Scripts & Makefile (requires Story 1.2, Story 1.3)
6. Story 1.6: MCP Server Foundation (requires Story 1.2, Story 1.4)

### Phase 2: Core Backend (Week 3-4)
7. Story 2.1: Backend API Foundation (requires Story 1.2, Story 1.4)
8. Story 2.2: LLM Client Setup & Provider Management (requires Story 2.1)
9. Story 2.3: SSE Streaming Support (requires Story 2.2)
10. Story 2.4: Function Calling for MCP Tools (requires Story 2.2, Story 1.6)
11. Story 2.5: Conversation State Management (requires Story 2.1) - **Can run in parallel with 2.2-2.4**
12. Story 2.6: Error Handling Patterns (requires Story 2.1, Story 2.2) - **Can run in parallel with 2.3-2.5**

### Phase 3: Memory & Tools (Week 5-6)
13. Story 3.1: Memory Storage Integration (requires Story 2.4, Story 1.6)
14. Story 3.2: Memory Retrieval for Decision Support (requires Story 3.1)
15. Story 4.1: Internet Access Tool (requires Story 2.4, Story 1.6) - **Can run in parallel with 3.1**
16. Story 4.2: Stock Trader Tool - Market Analysis (requires Story 2.4, Story 1.6) - **Can run in parallel with 3.1, 4.1**
17. Story 4.3: Stock Trader Tool - Personalized Recommendations (requires Story 4.2, Story 3.2)

### Phase 4: Telegram Bot (Week 7-8)
18. Story 5.1: Telegram Bot Setup & Message Reception (requires Story 2.1, Story 1.2)
19. Story 5.2: Streaming Response Delivery (requires Story 5.1, Story 2.3)
20. Story 5.3: Message Formatting & Error Handling (requires Story 5.2)

### Phase 5: Integration & Quality (Week 9-10)
21. Story 6.1: End-to-End Integration (requires Epics 1-5 complete)
22. Story 6.2: Unit & Integration Testing (requires Story 6.1)
23. Story 6.3: Error Scenario & Performance Testing (requires Story 6.2)
24. Story 6.4: Documentation & Deployment Readiness (requires Story 6.3)

---

## Acceptance Criteria Summary

**Total Stories:** 24 stories  
**Total Acceptance Criteria:** ~140 ACs across all stories  
**Coverage:** All PRD V1.0 requirements mapped to stories

**Key AC Patterns:**
- Functional: "Given X, when Y, then Z"
- Performance: Specific metrics (<500ms, <5s, etc.) with p95/p99 targets
- Error Handling: Graceful degradation scenarios with user-friendly messages
- Integration: End-to-end flow validation
- Security: Secrets management, input validation, error message sanitization

**Story Size Distribution:**
- Small (1-2 points): 8 stories
- Medium (3 points): 12 stories
- Large (4-5 points): 4 stories

**Parallelization Opportunities:**
- Phase 1: Stories 1.3 and 1.4 can run in parallel
- Phase 2: Story 2.5 can run in parallel with 2.2-2.4; Story 2.6 can run in parallel with 2.3-2.5
- Phase 3: Stories 3.1, 4.1, and 4.2 can run in parallel

---

## Next Steps

1. **Review Epic/Story Breakdown** - Validate structure, acceptance criteria, and sequencing
2. **Proceed to Sprint Planning** - Create sprint plan with prioritized stories and parallelization
3. **Begin Implementation** - Start with Story 1.1 (Project Structure & Repository Setup)

---

_This epic/story breakdown maps PRD requirements to implementable stories with clear acceptance criteria, enhanced with detailed ACs, missing stories, and improved sequencing._

_For implementation: Use the `create-story` workflow to generate detailed story implementation plans from this breakdown._
