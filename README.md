# Annie - Personal AI Companion

> A personal AI companion chatbot that provides decision-making support through intelligent, context-aware advice powered by real-time information, persistent memory, and specialized investment tools.

## Overview

Annie is a personal AI companion chatbot that provides decision-making support across financial, career, life, and business decisions. Built with advanced LLM integration, persistent memory, and real-time information access.

**Implemented Features (V1.0):**
- **LLM Integration** - Grok-4 (primary), Gemini 3 Pro, ChatGPT-5 with streaming responses
- **Persistent Memory** - agentic-memories integration for context-aware conversations
- **User Profiles** - Automatic extraction of preferences, goals, and background from conversations
- **Portfolio Management** - Track stock holdings, calculate performance, gain/loss metrics
- **Stock Analysis** - Real-time prices, technicals (RSI, moving averages), fundamentals via yfinance
- **Grok Live Search** - Real-time internet access for time-sensitive queries
- **LLM Observability** - Full tracing via Langfuse (costs, latency, token usage)
- **Telegram Interface** - Primary user interface with streaming responses

## Project Status

**Current Phase**: V1.0 MVP - Feature Complete, Optimizing

- [x] Core infrastructure (Docker, Redis, health checks)
- [x] LLM integration with streaming (Grok-4, Gemini, ChatGPT-5)
- [x] Memory storage and retrieval (agentic-memories)
- [x] User profile extraction and caching
- [x] Portfolio management tools (CRUD + price enrichment)
- [x] Stock market analysis tools
- [x] Langfuse observability integration
- [x] Telegram bot with SSE streaming
- [ ] Architecture simplification (in planning - see below)

## Documentation

See [`docs/`](./docs/) for comprehensive documentation:

**Planning Documents:**
- **[Product Requirements Document (PRD)](./docs/01-product/PRODUCT_REQUIREMENTS.md)** - Product vision, value proposition, target users, and requirements
- **[Architecture Plan](./docs/02-architecture/ARCHITECTURE_PLAN.md)** - System architecture, service design, data flow, and communication patterns
- **[Epic and Story Breakdown](./docs/epics-and-stories.md)** - Complete epic/story breakdown with acceptance criteria

**Implementation Documents:**
- **[Sprint Plan](./docs/04-implementation/SPRINT_PLAN.md)** - Sprint organization and timeline
- **[V1 Implementation Plan](./docs/04-implementation/V1_IMPLEMENTATION_PLAN.md)** - Implementation roadmap and phases
- **[V1 Detailed Tasks](./docs/04-implementation/V1_DETAILED_TASKS.md)** - Granular task breakdown

**Reference Documents:**
- **[Deployment Plan](./docs/05-deployment/DEPLOYMENT_PLAN.md)** - Docker deployment and operations
- **[Future Features Plan](./docs/01-product/FUTURE_FEATURES_PLAN.md)** - Roadmap for V1.1+
- **[Research Summary](./docs/06-reference/RESEARCH_SUMMARY.md)** - Comprehensive research reference

## Quick Start

**Prerequisites**:
- Docker 20.10+ and Docker Compose 2.0+
- Python 3.12+ (for local development)
- API Keys: XAI (Grok-4), Telegram Bot Token, Brave Search API, Stock API
- agentic-memories service running (for memory features)

**Setup** (once implementation is complete):

```bash
# Clone repository
git clone https://github.com/yourusername/annie.git
cd annie

# Run setup script (creates .env interactively and starts services)
./run_docker.sh

# Or manually:
# 1. Copy env.example to .env
# 2. Configure API keys and service URLs
# 3. Start services
make start

# View logs
make logs

# View specific service logs
make logs SERVICE=backend

# Stop services
make stop

# Clean up
make clean
```

**Note**: The `run_docker.sh` script and `Makefile` will be created in Story 1.5. For now, setup instructions are documented here.

## V1 Scope

**Core Features**:
1. **MCP Server** - Tool hosting and execution
2. **Backend API** - Chat logic and LLM integration
3. **Telegram Bot** - User interface via Telegram
4. **Internet Access Tool** - Web search via Brave Search
5. **Memories Tool** - agentic-memories integration

**Out of Scope for V1**:
- Web interface (V1.1)
- iOS app (V1.2)
- 3D animation (V2.0+)
- Voice interaction (V2.0+)
- A2A protocol (V2.1+)

## Architecture

### Current Architecture (4 Containers)

```
┌─────────────────┐
│  Telegram Bot   │ Container 3
└────────┬────────┘
         │ HTTP
         ▼
┌─────────────────┐     ┌─────────────┐
│  Backend API    │────▶│    Redis    │ Container 4
│   (Port 8001)   │     │ (Port 6380) │
└────────┬────────┘     └─────────────┘
         │ HTTP (JSON-RPC 2.0)
         ▼
┌─────────────────┐
│   MCP Server    │ Container 2
│   (Port 8002)   │
└────────┬────────┘
         │ HTTP
         ▼
┌─────────────────────────────────┐
│       External Services         │
│  - agentic-memories (6+ containers)
│  - Grok-4 / Gemini / ChatGPT-5 APIs
│  - Yahoo Finance (yfinance)
│  - Langfuse (observability)
└─────────────────────────────────┘
```

**Container Summary:**
| Container | Purpose | Port |
|-----------|---------|------|
| Backend | FastAPI - chat logic, LLM integration, streaming | 8001 |
| MCP Server | FastAPI - tool hosting (11 tools) | 8002 |
| Telegram Bot | User interface, message forwarding | - |
| Redis | Session state, price caching | 6380 |

### Planned Simplification

**Problem**: Running Annie requires 4 containers + agentic-memories (6+ containers) = 10+ containers for a personal app. This is resource-heavy for single-user deployment.

**Solution**: Merge MCP Server into Backend (in-process tool calls instead of HTTP).

```
Target Architecture (3 Containers):
┌─────────────────┐
│  Telegram Bot   │
└────────┬────────┘
         │ HTTP
         ▼
┌─────────────────┐     ┌─────────────┐
│  Backend API    │────▶│    Redis    │
│  + MCP Tools    │     └─────────────┘
│  (in-process)   │
└────────┬────────┘
         │ HTTP
         ▼
    External Services
```

**Benefits**: -1 container, -1 network hop, simpler deployment, lower memory footprint.

## Technology Stack

**Backend**:
- FastAPI (Python 3.12+)
- Redis (state management, price caching)
- Docker / Docker Compose

**LLM Integration**:
- Grok-4 (primary) with Live Search
- Gemini 3 Pro (alternative)
- ChatGPT-5 (fallback)
- Streaming via SSE

**MCP Server** (11 tools):
- FastAPI with JSON-RPC 2.0
- HTTP transport between containers
- Tools: health_check, store_memory, retrieve_memories, get_user_profile, get_portfolio, add_holding, update_holding, remove_holding, clear_portfolio, get_stock_data, get_stock_history

**Observability**:
- Langfuse for LLM tracing
- Automatic cost tracking
- Session-linked traces

**External Services**:
- agentic-memories (memory management, user profiles, portfolios)
- Telegram Bot API
- Yahoo Finance (stock data via yfinance)

## Project Structure

```
annie/
├── backend/              # FastAPI backend service
│   ├── api/              # API routes, LLM client, memory manager
│   │   ├── routes/       # chat.py, stream.py, health.py
│   │   ├── llm_client.py # Grok/Gemini/ChatGPT integration
│   │   ├── mcp_client.py # HTTP client for MCP server
│   │   ├── memory.py     # MemoryManager orchestration
│   │   └── profile.py    # User profile caching
│   ├── Dockerfile
│   └── requirements.txt
├── mcp_server/           # MCP tool server (11 tools)
│   ├── server.py         # FastAPI + JSON-RPC 2.0
│   ├── tools.py          # Tool implementations (~2400 lines)
│   ├── config.py
│   ├── Dockerfile
│   └── requirements.txt
├── telegram_bot/         # Telegram interface
│   ├── bot.py            # Message handling, SSE streaming
│   ├── Dockerfile
│   └── requirements.txt
├── scripts/              # Operational scripts
│   └── run_docker.sh     # Main startup script
├── docs/                 # Documentation
├── docker-compose.yml    # 4-service orchestration
├── Makefile              # Development commands
├── CLAUDE.md             # AI assistant context
└── env.example           # Environment template
```

**Development Commands**:
```bash
make start              # Start all services
make stop               # Stop all services
make restart            # Restart services
make rebuild            # Rebuild containers
make logs               # View all logs
make logs SERVICE=backend  # View specific service logs
make health             # Check service health
make shell SERVICE=backend # Debug shell access
make clean              # Clean up Docker resources
```

## Environment Setup

### Quick Start

1. **Copy environment template**:
   ```bash
   cp env.example .env
   ```

2. **Edit `.env` file** and fill in your API keys and tokens:
   - `TELEGRAM_BOT_TOKEN` - Get from [@BotFather](https://t.me/BotFather)
   - `GROK_API_KEY` or `CHATGPT_API_KEY` - Based on your `LLM_PROVIDER` choice
   - `AGENTIC_MEMORIES_URL` - URL to your agentic-memories service
   - `BRAVE_SEARCH_API_KEY` - Get from [Brave Search API](https://brave.com/search/api/)
   - `STOCK_API_KEY` - Your stock data provider API key

3. **Start services**:
   ```bash
   ./scripts/run_docker.sh
   ```
   
   Or use Docker Compose directly:
   ```bash
   docker-compose up --build
   ```

### Environment Variables

**Required**:
- `TELEGRAM_BOT_TOKEN` - Telegram bot token
- `AGENTIC_MEMORIES_URL` - agentic-memories service URL
- `AUTHORIZED_USER_IDS` - Comma-separated Telegram user IDs allowed to use the bot

**LLM Provider** (at least one required):
- `LLM_PROVIDER` - Primary provider: `grok-4`, `gemini`, or `chatgpt-5` (default: `grok-4`)
- `GROK_API_KEY` - Required if using Grok-4
- `GEMINI_API_KEY` - Required if using Gemini
- `CHATGPT_API_KEY` - Required if using ChatGPT-5

**Observability** (recommended):
- `LANGFUSE_PUBLIC_KEY` - Langfuse public key
- `LANGFUSE_SECRET_KEY` - Langfuse secret key
- `LANGFUSE_HOST` - Langfuse host (default: `https://us.cloud.langfuse.com`)

**Optional** (with defaults):
- `LOG_LEVEL` - `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (default: `INFO`)
- `ENVIRONMENT` - `dev`, `staging`, `prod` (default: `dev`)
- `BACKEND_PORT` - Backend API port (default: `8001`)
- `GROK_LIVE_SEARCH_MODE` - `auto`, `on`, `off` (default: `auto`)
- `GEMINI_MODEL` - Gemini model ID (default: `gemini-3.1-pro-preview`)

### Environment-Specific Configuration

The `ENVIRONMENT` variable controls runtime behavior:
- **dev**: Verbose logging, development features enabled
- **staging**: Production-like logging, staging features
- **prod**: Production logging, all features enabled

### Troubleshooting

**Missing environment variables**:
- Services will validate required variables on startup
- Check error messages for missing variables
- Ensure `.env` file exists and contains all required values

**Sensitive values in logs**:
- API keys and tokens are automatically masked in logs and error messages
- Only first 4 and last 4 characters are shown (e.g., `secr...2345`)

**`.env` file not found**:
- Run `./scripts/run_docker.sh` - it will prompt to create `.env` from `env.example`
- Or manually copy: `cp env.example .env`

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for contribution guidelines.

## License

[MIT License](./LICENSE)

## References

- [xAI Grok](https://grok.x.ai/) - Inspiration
- [agentic-memories](https://github.com/yourusername/agentic-memories) - Memory system
- [Model Context Protocol](https://modelcontextprotocol.io) - MCP specification
- [Langfuse](https://langfuse.com) - LLM observability

---

**Status**: V1.0 MVP Feature Complete - Architecture simplification in planning
