# Changelog

All notable changes to Annie will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Autonomous service with core loop, state machine, desire engine, and activity system (Epics 1-2)
- Genesis sequence: self-discovery, tool exploration, first journal, first outreach (Epic 3)
- Inbox system: webhooks, RSS feeds, Home Assistant events (Epic 4)
- Inner life: journal writing, creative production, adaptive schedule, sleep consolidation, personality engine (Epic 5)
- Outreach system with rate limiting, tool gating, and guardrails (Epic 6)
- Conversational context and memory integration (Epic 7)
- LLM provider registry supporting xAI, OpenAI, Google, Anthropic (Epic 9)
- File context sharing: images, documents, spreadsheets via Telegram (Epic 18)
- Home Assistant integration: voice messages, entity queries, device control (Epic 16)
- Extended MCP tools: web search, web crawl, Reddit search, profile updates (Epic 15)
- Langfuse integration for LLM observability and cost tracking
- Cloudflare Access authentication for web interface
- Docker Compose orchestration with health checks
- CI/CD with GitHub Actions (test, build, deploy)

## [1.0.0] - 2025-12-01

### Added
- Initial release
- Backend API with FastAPI
- MCP server with stdio transport
- Telegram bot interface
- Redis state management
- Memory storage via agentic-memories
- Grok-4 Live Search integration
- Structured logging with secret masking
- Environment validation and setup wizard
