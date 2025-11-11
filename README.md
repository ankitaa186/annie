# Annie - Personal AI Companion

> An AI companion chatbot inspired by Grok's Annie, designed to help friends and relatives make better decisions and achieve prosperity through intelligent, context-aware advice powered by real-time information, persistent memory, and specialized decision-making tools.

## Overview

Annie is a personal AI companion chatbot that provides decision-making support across financial, career, life, and business decisions. Built with advanced LLM integration, persistent memory, and real-time information access, Annie helps users make better decisions with 80% trust and coverage.

**Key Features:**
- **Decision-Making Support** - AI-powered analysis and recommendations for 80% of day-to-day decisions
- **MCP Server Integration** - Tool hosting for internet access and memory management
- **Intelligent Memory** - Powered by agentic-memories for persistent, context-aware conversations
- **Multi-Platform Access** - Telegram bot (V1), web interface (V1.1), iOS app (V1.2)
- **Advanced LLM Support** - Grok-4 primary, ChatGPT-5 fallback with streaming responses
- **Real-time Information** - Internet access via Brave Search for current data

## Project Status

**Current Phase**: V1.0 MVP - Implementation In Progress 🚧

- [x] Planning complete (PRD, Architecture, Epic/Story breakdown)
- [x] Sprint planning complete
- [x] Epic 1 tech context created
- [x] Story 1.1 drafted and ready for development
- [ ] V1.0 implementation (in progress)

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

```
┌─────────────────┐
│  Telegram Bot   │
└────────┬────────┘
         │ HTTP
         ▼
┌─────────────────┐
│  Backend API    │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌────────┐ ┌──────────┐
│  Redis │ │   MCP    │
└────────┘ └────┬─────┘
                │
         ┌──────┴──────┐
         │   Tools     │
         │ - Internet  │
         │ - Memories  │
         └─────────────┘
```

## Technology Stack

**Backend**:
- FastAPI (Python 3.12+)
- Redis (state management)
- Docker / Docker Compose

**LLM Integration**:
- Grok-4 (primary) / ChatGPT-5 (fallback)
- Streaming via SSE

**MCP Server**:
- Python MCP SDK
- Stdio transport
- Docker exec communication

**External Services**:
- Brave Search API (internet access)
- agentic-memories (memory management)
- Telegram Bot API

## Project Structure

```
annie/
├── backend/           # FastAPI backend service (Python 3.12+)
│   └── requirements.txt
├── mcp_server/        # MCP server with tools (Python 3.12+)
│   └── requirements.txt
├── telegram_bot/      # Telegram bot service (Python 3.12+)
│   └── requirements.txt
├── scripts/           # Operational scripts (run_docker.sh, etc.)
├── docs/              # Documentation
│   ├── 01-product/    # Product requirements and planning
│   ├── 02-architecture/ # Architecture and design
│   ├── 03-technical/  # Technical specifications
│   ├── 04-implementation/ # Implementation plans and tasks
│   ├── 05-deployment/ # Deployment guides
│   └── 06-reference/  # Research and reference materials
├── .gitignore         # Git exclusions
├── .dockerignore      # Docker build exclusions
├── README.md          # This file
├── docker-compose.yml # (Will be created in Story 1.2)
├── Dockerfile.*       # Service Dockerfiles (will be created in Story 1.2)
├── run_docker.sh      # Main startup script (will be created in Story 1.5)
├── Makefile           # Common commands (will be created in Story 1.5)
└── env.example        # Environment template (already exists)
```

**Directory Purpose**:
- **backend/**: FastAPI application handling HTTP requests, LLM integration, and state management
- **mcp_server/**: MCP protocol server hosting tools (internet search, memories, stock trading)
- **telegram_bot/**: Telegram bot service forwarding messages to backend and streaming responses
- **scripts/**: Operational scripts for development workflow automation
- **docs/**: Comprehensive project documentation including PRD, architecture, and implementation plans

**Development Commands** (once implemented):
- `make start` - Start all services via Docker Compose
- `make stop` - Stop all services gracefully
- `make logs` - View logs from all services
- `make logs SERVICE=backend` - View logs from specific service
- `make test` - Run test suite for all services
- `make clean` - Clean up Docker containers, volumes, and temporary files

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
- `TELEGRAM_BOT_TOKEN` - Telegram bot token (required)
- `AGENTIC_MEMORIES_URL` - agentic-memories service URL (required)
- `GROK_API_KEY` - Grok-4 API key (required if `LLM_PROVIDER=grok-4`)
- `CHATGPT_API_KEY` - ChatGPT-5 API key (required if `LLM_PROVIDER=chatgpt-5`)

**Optional** (with defaults):
- `LLM_PROVIDER` - Primary LLM provider: `grok-4` or `chatgpt-5` (default: `grok-4`)
- `LOG_LEVEL` - Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (default: `INFO`)
- `ENVIRONMENT` - Environment type: `dev`, `staging`, `prod` (default: `dev`)
- `BACKEND_PORT` - Backend API port (default: `8000`)
- `REDIS_HOST` - Redis hostname (default: `redis`)
- `REDIS_PORT` - Redis port (default: `6379`)

**Tool API Keys** (required for specific features):
- `BRAVE_SEARCH_API_KEY` - Required for internet access tool
- `STOCK_API_KEY` - Required for stock trader tool

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

See [CONTRIBUTING.md](./CONTRIBUTING.md) for contribution guidelines and [V1 Implementation Plan](./docs/04-implementation/V1_IMPLEMENTATION_PLAN.md) for development roadmap.

## License

[MIT License](./LICENSE)

## References

- [xAI Grok](https://grok.x.ai/) - Inspiration
- [agentic-memories](https://github.com/yourusername/agentic-memories) - Memory system
- [Model Context Protocol](https://modelcontextprotocol.io) - MCP specification

---

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for contribution guidelines.

## License

[MIT License](./LICENSE)

---

**Status**: V1.0 MVP - Implementation in progress. Story 1.1 (Project Structure) complete ✅
