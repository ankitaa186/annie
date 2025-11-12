# V1 Implementation Plan

## Decision-Making Architecture

**Core Principle**: agentic-memories provides the backbone for all decision-making capabilities in V1.0.

**Decision Flow**:
1. User asks for decision help
2. Annie retrieves relevant memories from agentic-memories (past decisions, outcomes, preferences)
3. Annie gathers real-time information via Internet Access tool if needed
4. Annie analyzes options with pros/cons using memory context
5. Annie provides recommendation with reasoning based on user's history
6. Annie stores decision context in agentic-memories for future learning

**agentic-memories Integration**:
- Stores conversation context and decisions
- Retrieves relevant past decisions and outcomes
- Maintains user preferences and risk profiles
- Enables personalized recommendations
- Supports learning from decision patterns

## V1.0 Scope

### Core Components

1. **MCP Server** - Tool hosting and execution
2. **Backend API** - Core chat logic and LLM integration
3. **Telegram Bot** - User interface via Telegram
4. **Internet Access Tool** - Web search capability
5. **Memories Tool** - agentic-memories integration
6. **Stock Trader Tool** - Stock market analysis and recommendations
7. **Decision Support** - Pros/cons analysis for user decisions
8. **Docker Infrastructure** - Containerized deployment
9. **Redis State Management** - Session and conversation state (PostgreSQL deferred to V2.0)

### Out of Scope for V1.0

- Web interface (V1.1)
- iOS app (V1.2)
- PostgreSQL database (V2.0)
- 3D animation (V1.1)
- Voice interaction (V1.2)
- Multi-modality (V2.0)
- A2A protocol integration (V2.1)
- Advanced gamification features (V2.0)

## Detailed Task Breakdown

For granular, actionable tasks broken down into 1-2 day increments, see [V1 Detailed Tasks](./V1_DETAILED_TASKS.md).

**Summary**:
- **50 tasks** across 5 phases
- Each task: 1-2 days duration
- Clear deliverables and dependencies
- Total duration: ~10 weeks

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

**Goal**: Implement core MCP tools including Stock Trader

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

3. **Stock Trader Tool**
   - **Implementation**: Separate MCP tool (`stock_trader`)
   - Stock market data API integration (Alpha Vantage/Polygon.io/Finnhub)
   - Real-time stock price lookup
   - Market analysis function
   - Stock recommendation function
   - Risk assessment
   - Portfolio analysis integration
   - Historical data analysis

4. **Tool Registration**
   - Register all tools in MCP server
   - Tool schemas
   - Input validation

**Deliverables**:
- Internet search tool working
- Memories tool working
- Stock Trader tool working (separate MCP tool with dedicated API)
- All tools callable via MCP

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

**Decision**: Redis-only for V1.0, PostgreSQL added in V2.0

**Rationale**:
- Redis fast for sessions and cache
- Simplifies V1.0 implementation
- PostgreSQL adds persistence in V2.0
- V1.0 focuses on functionality over persistence

**Implementation V1.0**:
- Redis: Sessions, conversation cache, real-time state, temporary history
- TTL-based expiration for old data
- agentic-memories provides long-term memory storage

**Implementation V2.0**:
- PostgreSQL: Persistent conversation history, user preferences, decision outcomes
- Redis: Hot cache layer
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
│   │   ├── memories.py
│   │   └── stock_trader.py   # Stock Trader tool
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
- `STOCK_API_KEY` - Stock market API key (Alpha Vantage/Polygon.io)
- `LLM_PROVIDER` - Primary LLM provider (default: grok4)
- `LOG_LEVEL` - Logging level (default: INFO)

## Success Criteria

### Functional Requirements

- [ ] User can send messages via Telegram
- [ ] Bot responds with streaming text
- [ ] Internet search tool works
- [ ] Memories tool stores and retrieves memories
- [ ] **Stock Trader tool provides market analysis**
- [ ] LLM uses tools when appropriate
- [ ] Basic pros/cons analysis for decisions works
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

### Error Handling Strategy

**Decision**: Basic error handling for V1.0 - focus on features, polish later

**Approach**:
- Handle happy path well
- Graceful errors with user-friendly messages
- Basic fallbacks for critical failures
- Comprehensive error handling deferred to V2.0

**Error Scenarios**:

1. **agentic-memories Down**:
   - Graceful degradation: Continue without memory retrieval
   - User-friendly message: "Memory service temporarily unavailable, continuing without context"
   - Store conversation locally in Redis for later sync

2. **LLM API Fails**:
   - Automatic fallback to ChatGPT-5 if Grok-4 fails
   - User-friendly message: "Switching to backup service"
   - If both fail: Clear error message, suggest retry

3. **Internet Search Fails**:
   - Continue without real-time data
   - User-friendly message: "Unable to fetch current data, using available information"
   - Provide recommendation based on available context

4. **Stock API Fails**:
   - Fallback to internet search for stock data
   - User-friendly message: "Using alternative data source"
   - Basic analysis without real-time prices if needed

### Decision Tracking

**Decision**: No outcome tracking in V1.0 - defer to V2.0

**V1.0 Approach**:
- Annie provides advice and recommendations
- Stores conversation context in agentic-memories
- No explicit outcome tracking
- No feedback mechanism
- Focus on providing quality advice

**V2.0 Enhancement**:
- Track decision outcomes
- User feedback mechanism (explicit + implicit)
- Learn from what worked/didn't work
- Use outcomes for future recommendations
- Advanced learning from decision patterns

## Version Roadmap

### V1.0 (Current)
- Telegram bot
- MCP server with Internet, Memories, Stock Trader tools
- Redis state management
- Basic decision support

### V1.1: Web Interface
- React/Next.js web interface
- 3D avatar (React Three Fiber)
- SSE streaming support
- Mobile responsive

### V1.2: iOS App
- Native iOS app (SwiftUI)
- 3D avatar (SceneKit)
- Voice interaction
- Push notifications

### V2.0: Advanced Features
- PostgreSQL database for persistence
- Multi-modality (images, voice understanding)
- Advanced decision frameworks
- **Decision outcome tracking and learning**
- Enhanced gamification
- WebSocket support

### V2.1: A2A Protocol
- A2A protocol integration
- Claude/Gemini integration
- Agent registry

### V3.0: Advanced AI
- Fine-tuning for character
- Deep personalization
- Advanced memory capabilities

## References

- [V1/V2 Definition](./V1_V2_DEFINITION.md) - Clear version boundaries
- [Architecture Plan](../02-architecture/ARCHITECTURE_PLAN.md) - System architecture
- [Product Requirements](../01-product/PRODUCT_REQUIREMENTS.md) - Product vision
- [Future Features Plan](../01-product/FUTURE_FEATURES_PLAN.md) - V1.1+ roadmap

