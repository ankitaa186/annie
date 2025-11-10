# V1 Implementation Plan

## Overview

This document outlines the implementation plan for Annie chatbot V1, focusing on core functionality: MCP Server, Internet Access Tool, Telegram Bot, and agentic-memories integration.

## V1 Scope

### Core Components

1. **MCP Server** - Tool hosting and execution
2. **Backend API** - Core chat logic and LLM integration
3. **Telegram Bot** - User interface via Telegram
4. **Internet Access Tool** - Web search capability
5. **Memories Tool** - agentic-memories integration
6. **Docker Infrastructure** - Containerized deployment

### Out of Scope for V1

- Web interface
- iOS app
- A2A protocol integration
- 3D animation
- Voice interaction
- Advanced gamification features

## Implementation Phases

### Phase 1: Foundation (Week 1-2)

**Goal**: Set up basic infrastructure and MCP server

**Tasks**:
1. **Project Structure**
   - Create directory structure
   - Set up Python environments
   - Initialize git repository

2. **Docker Setup**
   - Create `docker-compose.yml`
   - Create Dockerfiles (backend, mcp-server, telegram-bot)
   - Create `run_docker.sh` script
   - Create `Makefile`
   - Create `env.example`

3. **MCP Server Foundation**
   - Install MCP Python SDK
   - Create basic MCP server structure
   - Implement stdio transport
   - Add health check tool
   - Test MCP server locally

**Deliverables**:
- Docker services running
- MCP server responding to basic tool calls
- Operational scripts working

### Phase 2: Core Backend (Week 3-4)

**Goal**: Implement backend API with LLM integration

**Tasks**:
1. **Backend API Setup**
   - FastAPI application structure
   - Health check endpoint
   - Basic routing

2. **LLM Client**
   - Unified LLM client (Grok-4 primary, ChatGPT-5 fallback)
   - SSE streaming support
   - Function calling support
   - Error handling and retries
   - Token usage tracking

3. **MCP Client Integration**
   - Docker exec pattern for MCP communication
   - Tool calling wrapper
   - Error handling

4. **State Management**
   - Redis connection
   - Session management
   - Conversation state storage

**Deliverables**:
- Backend API running
- LLM streaming working
- MCP tool calls functional
- Basic state management

### Phase 3: MCP Tools (Week 5-6)

**Goal**: Implement core MCP tools

**Tasks**:
1. **Internet Access Tool**
   - Brave Search API integration
   - Rate limiting
   - Error handling
   - Result parsing

2. **Memories Tool**
   - agentic-memories API client
   - Store memory function
   - Retrieve memory function
   - Portfolio summary function
   - Error handling and fallbacks

3. **Tool Registration**
   - Register tools in MCP server
   - Tool schemas
   - Input validation

**Deliverables**:
- Internet search tool working
- Memories tool working
- Tools callable via MCP

### Phase 4: Telegram Bot (Week 7-8)

**Goal**: Implement Telegram bot interface

**Tasks**:
1. **Telegram Bot Setup**
   - Bot token configuration
   - Polling mechanism
   - Update handling

2. **Message Processing**
   - Receive user messages
   - Forward to backend API
   - Stream responses back
   - Handle long messages

3. **Backend Integration**
   - Telegram adapter in backend
   - Message formatting
   - Error handling

**Deliverables**:
- Telegram bot responding
- Messages flowing through backend
- Streaming responses working

### Phase 5: Integration & Testing (Week 9-10)

**Goal**: Integrate all components and test

**Tasks**:
1. **End-to-End Integration**
   - Full message flow
   - Tool chaining
   - Error scenarios

2. **Testing**
   - Unit tests
   - Integration tests
   - Error handling tests

3. **Documentation**
   - API documentation
   - Setup guide
   - Troubleshooting guide

**Deliverables**:
- Fully integrated system
- Test suite passing
- Documentation complete

## Technical Decisions

### MCP Server Communication

**Decision**: Use Docker exec pattern for V1

**Rationale**:
- Simplest to implement
- Works with stdio transport
- Can optimize later with HTTP bridge

**Implementation**:
- Backend uses `docker exec` to call MCP server
- MCP server runs in separate container
- Communication via stdio pipes

### LLM Provider

**Decision**: Grok-4 as primary, ChatGPT-5 as fallback

**Rationale**:
- Grok-4 has real-time data access
- ChatGPT-5 provides reliable fallback
- Both support OpenAI-compatible API

**Implementation**:
- Unified LLM client
- Provider selection via environment variable
- Automatic fallback on errors

### State Storage

**Decision**: Redis for hot data, PostgreSQL for cold data

**Rationale**:
- Redis fast for sessions and cache
- PostgreSQL persistent for history
- Hybrid approach balances speed and persistence

**Implementation**:
- Redis: Sessions, conversation cache, real-time state
- PostgreSQL: Conversation history, user preferences
- Sync mechanism between them

### Streaming

**Decision**: SSE for V1

**Rationale**:
- Simpler than WebSocket
- Automatic reconnection
- Sufficient for one-way streaming

**Implementation**:
- SSE endpoint for LLM responses
- HTTP POST for user messages
- Can upgrade to WebSocket later

## File Structure

```
annie/
├── backend/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py          # FastAPI app
│   │   ├── routes/
│   │   │   ├── chat.py
│   │   │   └── health.py
│   │   └── models/
│   ├── core/
│   │   ├── llm_client.py
│   │   ├── mcp_client.py
│   │   └── state_manager.py
│   └── requirements.txt
├── mcp_server/
│   ├── server.py            # MCP server main
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── internet_access.py
│   │   └── memories.py
│   └── requirements.txt
├── telegram_bot/
│   ├── bot.py               # Telegram bot main
│   ├── handlers/
│   └── requirements.txt
├── docker-compose.yml
├── Dockerfile.backend
├── Dockerfile.mcp-server
├── Dockerfile.telegram-bot
├── run_docker.sh
├── Makefile
├── env.example
└── README.md
```

## Environment Variables

**Required**:
- `XAI_API_KEY` - Grok-4 API key
- `TELEGRAM_BOT_TOKEN` - Telegram bot token
- `AGENTIC_MEMORIES_URL` - agentic-memories service URL

**Optional**:
- `OPENAI_API_KEY` - ChatGPT-5 fallback
- `BRAVE_API_KEY` - Brave Search API key
- `LLM_PROVIDER` - Primary LLM provider (default: grok4)
- `LOG_LEVEL` - Logging level (default: INFO)

## Success Criteria

### Functional Requirements

- [ ] User can send messages via Telegram
- [ ] Bot responds with streaming text
- [ ] Internet search tool works
- [ ] Memories tool stores and retrieves memories
- [ ] LLM uses tools when appropriate
- [ ] Fallback to ChatGPT-5 if Grok-4 fails
- [ ] Error handling for all failure scenarios

### Performance Requirements

- [ ] First token latency < 500ms
- [ ] Tool calls complete < 5 seconds
- [ ] System handles 100 concurrent users
- [ ] 99% uptime

### Operational Requirements

- [ ] Docker services start successfully
- [ ] Health checks pass
- [ ] Logs are structured and searchable
- [ ] Environment setup is automated

## Risk Mitigation

### Technical Risks

1. **MCP Docker Communication Complexity**
   - Mitigation: Start with Docker exec, plan HTTP bridge for future
   - Fallback: Direct HTTP calls if MCP proves too complex

2. **LLM API Rate Limits**
   - Mitigation: Implement rate limiting and queuing
   - Fallback: Multiple API keys, provider rotation

3. **agentic-memories Service Unavailable**
   - Mitigation: Graceful degradation, local cache
   - Fallback: Continue without memories feature

### Operational Risks

1. **Docker Setup Complexity**
   - Mitigation: Comprehensive `run_docker.sh` script
   - Fallback: Manual setup instructions

2. **Environment Variable Management**
   - Mitigation: Interactive `.env` creation
   - Fallback: Documentation for manual setup

## Next Steps After V1

1. **V1.1**: Add web interface
2. **V1.2**: Add iOS app
3. **V2.0**: Add WebSocket support, advanced features
4. **V2.1**: Add A2A protocol integration
5. **V3.0**: Add 3D animation, voice interaction

## References

- MCP_SERVER_RESEARCH.md: MCP implementation details
- LLM_INTEGRATION_RESEARCH.md: LLM integration patterns
- DOCKER_ARCHITECTURE_RESEARCH.md: Docker setup
- AGENTIC_MEMORIES_INTEGRATION.md: Memories integration
- EXTERNAL_APIS_RESEARCH.md: External API integration

