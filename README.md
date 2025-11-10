# Annie Chatbot

> An AI companion chatbot inspired by Grok's Annie, featuring MCP server integration, memory management, and multi-platform support.

## Overview

Annie is a chatbot with:
- **MCP Server Integration** - Tool hosting for internet access and memory management
- **Intelligent Memory** - Powered by agentic-memories for persistent, context-aware conversations
- **Multi-Platform Access** - Telegram bot, web interface (future), iOS app (future)
- **Advanced LLM Support** - Grok-4 primary, ChatGPT-5 fallback
- **Real-time Streaming** - Low-latency response generation

## Project Status

**Current Phase**: Planning Complete ✅

- [x] Research complete (12 research areas)
- [x] Planning documents created
- [ ] V1 implementation (in progress)

## Documentation

See [`docs/`](./docs/) for comprehensive documentation:

- **[V1 Implementation Plan](./docs/04-implementation/V1_IMPLEMENTATION_PLAN.md)** - Implementation roadmap and phases
- **[Architecture Plan](./docs/02-architecture/ARCHITECTURE_PLAN.md)** - System architecture and design
- **[Deployment Plan](./docs/05-deployment/DEPLOYMENT_PLAN.md)** - Docker deployment and operations
- **[Product Requirements](./docs/01-product/PRODUCT_REQUIREMENTS.md)** - Product vision and requirements
- **[Future Features Plan](./docs/01-product/FUTURE_FEATURES_PLAN.md)** - Roadmap for V1.1+
- **[Research Summary](./docs/06-reference/RESEARCH_SUMMARY.md)** - Comprehensive research reference

## Quick Start

**Prerequisites**:
- Docker and Docker Compose
- Python 3.12+
- API Keys: XAI (Grok-4), Telegram Bot Token
- agentic-memories service running (for memory features)

**Setup** (once implementation is complete):

```bash
# Clone repository
git clone https://github.com/yourusername/annie.git
cd annie

# Run setup script (creates .env interactively)
./run_docker.sh

# Or manually:
# 1. Copy env.example to .env
# 2. Configure API keys
# 3. Start services
make start

# View logs
make logs

# Stop services
make stop
```

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

## Development

**Project Structure**:
```
annie/
├── backend/          # Backend API service
├── mcp_server/       # MCP server and tools
├── telegram_bot/     # Telegram bot service
├── scripts/          # Operational scripts
├── docs/             # Documentation
├── docker-compose.yml
├── Dockerfile.*      # Service Dockerfiles
├── run_docker.sh     # Main startup script
├── Makefile          # Common commands
└── env.example       # Environment template
```

**Commands** (once implemented):
- `make help` - Show available commands
- `make start` - Start all services
- `make stop` - Stop all services
- `make logs` - View logs
- `make test` - Run tests
- `make clean` - Clean up

## Environment Variables

**Required**:
- `XAI_API_KEY` - Grok-4 API key
- `TELEGRAM_BOT_TOKEN` - Telegram bot token
- `AGENTIC_MEMORIES_URL` - agentic-memories service URL

**Optional**:
- `OPENAI_API_KEY` - ChatGPT-5 fallback
- `BRAVE_API_KEY` - Brave Search API
- `LLM_PROVIDER` - Primary LLM (default: grok4)
- `LOG_LEVEL` - Logging level (default: INFO)

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for contribution guidelines and [V1 Implementation Plan](./docs/04-implementation/V1_IMPLEMENTATION_PLAN.md) for development roadmap.

## License

[MIT License](./LICENSE)

## References

- [xAI Grok](https://grok.x.ai/) - Inspiration
- [agentic-memories](https://github.com/yourusername/agentic-memories) - Memory system
- [Model Context Protocol](https://modelcontextprotocol.io) - MCP specification

---

**Status**: Planning phase complete, implementation starting soon.
