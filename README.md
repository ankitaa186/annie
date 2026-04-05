# Annie - Personal AI Companion

> A personal AI companion that remembers everything, searches the web, manages your portfolio, controls your smart home, understands files you share, and reaches out proactively when something matters.

## What Annie Can Do

### Conversation & Intelligence
- **Multi-provider LLM** — Grok-4, Gemini 3.1 Pro, ChatGPT-5 with automatic failover and streaming responses
- **Persistent Memory** — Remembers conversations, decisions, preferences, and context across sessions via agentic-memories
- **User Profiles** — Automatically builds and updates a profile of your goals, interests, risk tolerance, and background
- **File Understanding** — Share images, PDFs, spreadsheets, Word docs, and CSVs via Telegram for multimodal analysis (up to 10 files per message)

### Research & Information
- **Web Search** — Real-time web search via Tavily (primary) with DuckDuckGo fallback
- **Web Crawl** — Fetch and parse full webpage content from URLs you share (crawl4ai + Jina Reader fallback)
- **Reddit Search** — Search Reddit for community opinions and discussions (PRAW + JSON API fallback)
- **Grok Live Search** — Real-time internet access built into Grok-4 for time-sensitive queries

### Finance & Portfolio
- **Portfolio Management** — Track stock holdings, cost basis, and calculate performance with real-time prices
- **Stock Analysis** — Real-time prices, technicals (RSI, moving averages, MACD), and fundamentals via yfinance
- **Decision Support** — Annie remembers your risk tolerance and investment goals to provide personalized analysis

### Smart Home (Home Assistant)
- **Query Devices** — Check status of lights, sensors, thermostats, locks, and any Home Assistant entity
- **Control Devices** — Turn on/off lights, set temperatures, adjust covers (restricted to admin users and allowlisted entities)
- **Voice Messages** — Send voice messages to Alexa devices with emotional delivery (whisper, excited, conversational, etc.)

### Proactive Outreach
- **Intent-driven Messages** — Annie reaches out via Telegram when something matters (price alerts, reminders, insights)
- **Smart Gating** — Rate limiting, quiet hours, daily caps, and cooldowns prevent notification spam
- **Subconscious Processing** — Background worker monitors triggers from agentic-memories and fires when conditions are met

### Observability & Security
- **LLM Tracing** — Full request tracing via Langfuse (costs, latency, token usage, tool calls)
- **Admin Controls** — Smart home and terminal tools restricted to `ADMIN_USER_IDS`
- **User Authorization** — Telegram whitelist via `AUTHORIZED_USER_IDS`, Cloudflare Access for web UI
- **API Key Masking** — All sensitive values automatically masked in logs

## Project Status

**Current Phase**: V1.0 Complete, V2 Autonomous Architecture In Progress

- [x] Core infrastructure (Docker, Redis, health checks)
- [x] Multi-provider LLM with streaming (Grok-4, Gemini 3.1 Pro, ChatGPT-5)
- [x] LLM Provider Registry with automatic failover (Epic 9)
- [x] Memory storage and retrieval (agentic-memories)
- [x] User profile extraction and caching
- [x] Portfolio management and stock analysis tools
- [x] Langfuse observability integration
- [x] Telegram bot with SSE streaming and file sharing (Epic 18)
- [x] Web search, web crawl, and Reddit search tools (Epic 15)
- [x] Home Assistant integration — query, control, voice messages (Epic 16)
- [x] Proactive outreach system with smart gating (Epic 6)
- [ ] Dashboard UI (Epic 8 — backlog)
- [ ] V2 autonomous chat brain (Epic 10 — backlog)

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
- Python 3.12+ (for setup wizard)
- Docker 20.10+ and Docker Compose 2.0+
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- At least one LLM API key (xAI, Google AI, or OpenAI)

**Setup**:

```bash
# Clone repository
git clone https://github.com/ankitaa186/annie.git
cd annie

# Recommended: Run the interactive setup wizard
# Checks prerequisites, creates .env, validates API keys, and starts services
make setup

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

## MCP Tools (28 registered)

| Category | Tools |
|----------|-------|
| **Memory** | `store_memory`, `retrieve_memories`, `delete_memory` |
| **Profile** | `get_user_profile`, `update_user_profile` |
| **Portfolio** | `get_portfolio`, `add_holding`, `update_holding`, `remove_holding`, `clear_portfolio` |
| **Stock Data** | `get_stock_data`, `get_stock_history` |
| **Web** | `web_search`, `web_crawl`, `reddit_search` |
| **Smart Home** | `home_assistant_query`, `home_assistant_control`, `send_voice_message_to_smart_home` |
| **System** | `health_check`, `execute_command` (admin-only) |

## Architecture

### Architecture (6 Containers)

```
┌─────────────────┐     ┌─────────────┐
│  Telegram Bot   │     │   Web UI    │
└────────┬────────┘     └──────┬──────┘
         │ HTTP                │ HTTP (Cloudflare Access)
         ▼                     ▼
┌──────────────────────────────────────┐     ┌─────────────┐
│            Backend API               │────▶│    Redis    │
│           (Port 8001)                │     └─────────────┘
└──────┬───────────────────┬───────────┘
       │ HTTP              │ HTTP
       ▼                   ▼
┌─────────────┐   ┌──────────────────────────────┐
│ MCP Server  │   │      External Services        │
│ (Port 8002) │   │  - agentic-memories           │
│  28 tools   │   │  - Grok-4 / Gemini / ChatGPT  │
└──────┬──────┘   │  - Home Assistant              │
       │ HTTP     │  - Yahoo Finance / Tavily      │
       ▼          │  - Langfuse                    │
  Home Assistant  └──────────────────────────────────┘
  Tavily / DDG
  agentic-memories
```

| Container | Purpose | Port |
|-----------|---------|------|
| Backend | FastAPI — chat logic, LLM integration, streaming, proactive worker | 8001 |
| MCP Server | FastAPI — 28 MCP tools via JSON-RPC 2.0 | 8002 |
| Telegram Bot | User interface, file handling, message forwarding | - |
| Proactive Worker | Background trigger polling, intent processing, Telegram delivery | - |
| Web UI | Nginx — static frontend (Cloudflare Access protected) | 3001 |
| Redis | Session state, caching, queues, circuit breakers | 6380 |

## Technology Stack

**Backend**:
- FastAPI (Python 3.12+), Redis, Docker Compose
- SSE streaming, background workers (SAQ)

**LLM Providers** (automatic failover):
- Grok-4 / Grok-4 Fast (xAI) — with Live Search
- Gemini 3.1 Pro Preview (Google) — multimodal, context caching
- GPT-5.4 (OpenAI) — large output capacity

**MCP Server** (28 tools):
- FastAPI with JSON-RPC 2.0, HTTP transport
- Memory, profile, portfolio, stock, web search, web crawl, Reddit, Home Assistant, voice, terminal

**Observability**: Langfuse (tracing, cost tracking, session-linked spans)

**External Services**:
- agentic-memories (memory, profiles, portfolios, intents)
- Home Assistant (smart home control + Alexa voice)
- Tavily / DuckDuckGo (web search), crawl4ai / Jina Reader (web crawl)
- Yahoo Finance (stock data), Telegram Bot API

## Project Structure

```
annie/
├── backend/                # FastAPI backend service
│   ├── api/
│   │   ├── routes/         # chat.py, stream.py, conversations.py, health.py
│   │   ├── providers/      # grok, gemini, chatgpt providers + registry
│   │   ├── middleware/      # cloudflare_auth.py, rate_limiter.py
│   │   ├── proactive/      # worker.py, agent.py, gate.py, telegram_delivery.py
│   │   ├── llm_client.py   # Multi-provider LLM client with failover
│   │   ├── mcp_client.py   # HTTP client for MCP server
│   │   ├── memory.py       # MemoryManager with retry + circuit breaker
│   │   ├── profile.py      # User profile caching
│   │   └── prompts.py      # System prompt builder
│   └── Dockerfile
├── mcp_server/             # MCP tool server (28 tools)
│   ├── server.py           # FastAPI + JSON-RPC 2.0
│   ├── tools/              # Tool modules (memory, profile, web, HA, etc.)
│   ├── config.py           # ADMIN_USER_IDS, HA config, API keys
│   └── Dockerfile
├── telegram_bot/           # Telegram interface
│   ├── handlers/           # Message, voice, photo, document handlers
│   ├── file_handler.py     # File download, validation, base64 encoding
│   ├── backend_client.py   # HTTP client for backend API
│   └── Dockerfile
├── scripts/
│   ├── setup_wizard.py     # Interactive first-boot setup
│   └── run_docker.sh       # Startup script
├── docker-compose.yml      # 6-service orchestration
├── Makefile                # make setup, start, stop, logs, test, etc.
└── env.example             # Environment template
```

**Development Commands**:
```bash
make setup              # Interactive first-boot setup wizard
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

The easiest way to set up Annie is with the interactive setup wizard:

```bash
make setup
```

This checks prerequisites (Docker, Python, etc.), walks you through creating `.env` with your API keys, validates connectivity, and optionally starts services.

**Manual setup** (if you prefer):

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
   make start
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

[Apache License 2.0](./LICENSE)

## References

- [xAI Grok](https://grok.x.ai/) - Inspiration
- [agentic-memories](https://github.com/ankitaa186/agentic-memories) - Memory system
- [Model Context Protocol](https://modelcontextprotocol.io) - MCP specification
- [Langfuse](https://langfuse.com) - LLM observability

---

**Status**: V1.0 Complete — 28 tools, 3 LLM providers, proactive outreach, smart home, file understanding
