# Epic Technical Specification: Foundation & Infrastructure

Date: 2025-11-10
Author: Ankit
Epic ID: 1
Status: Draft

---

## Overview

Epic 1 establishes the foundational infrastructure and development environment for Annie, enabling all subsequent development work. This epic focuses on project structure, Docker containerization, environment configuration, logging infrastructure, operational scripts, and MCP server foundation. As the first epic in the implementation phase, it creates the technical foundation that all other epics depend upon, ensuring a consistent, containerized development environment that supports hot-reload, proper service isolation, and standardized operational workflows.

The epic aligns with the PRD requirement for Docker deployment and MCP protocol integration, and implements the architecture's service containerization strategy. It establishes the development workflow that enables efficient parallel development across backend, MCP server, and Telegram bot services.

---

## Objectives and Scope

### In-Scope

- **Project Structure**: Complete directory structure with `backend/`, `mcp_server/`, `telegram_bot/`, `scripts/`, `docs/` directories
- **Docker Infrastructure**: Docker Compose configuration with all services (Backend API, MCP Server, Telegram Bot, Redis)
- **Environment Configuration**: Environment variable management with `env.example` template and `.env` file generation
- **Secrets Management**: Secure handling of API keys, tokens, and sensitive configuration
- **Logging Infrastructure**: Structured logging across all services with JSON format (production) and human-readable format (development)
- **Operational Scripts**: `run_docker.sh` script and Makefile with common development commands
- **MCP Server Foundation**: Basic MCP server with stdio transport, health check tool, and JSON-RPC 2.0 protocol support
- **Service Health Checks**: Docker health checks for all services
- **Development Volumes**: Hot-reload capability via Docker volume mounts

### Out-of-Scope

- **Production Deployment**: Production-specific configurations (deferred to deployment epic)
- **CI/CD Pipeline**: Continuous integration/deployment setup (deferred to later phase)
- **Monitoring Infrastructure**: Advanced monitoring beyond basic logging (deferred to Epic 6)
- **Database Setup**: PostgreSQL setup (deferred to V2.0 per PRD)
- **Service Authentication**: Inter-service authentication (V1 uses internal Docker network)
- **Load Balancing**: Load balancer configuration (single instance sufficient for V1)

---

## System Architecture Alignment

This epic implements the foundational components referenced in the Architecture Plan:

**Service Architecture Alignment:**
- **Backend API Service**: Dockerfile and service definition (FastAPI, Python 3.12+)
- **MCP Server Service**: Dockerfile and service definition (Python MCP SDK, stdio transport)
- **Telegram Bot Service**: Dockerfile and service definition (python-telegram-bot)
- **Redis Service**: Redis 7.2 container for state management

**Communication Patterns:**
- **Docker Network**: Isolated `annie-network` for inter-service communication
- **MCP Communication**: Stdio transport pattern via Docker exec (as specified in Architecture Plan)
- **Service Discovery**: Docker Compose service names for internal communication

**State Management Alignment:**
- **Redis Setup**: Redis container configured for hot data storage (sessions, conversation cache)
- **TTL Configuration**: Session expiration (1 hour) and cache TTL (30 minutes) as per architecture

**Security Architecture Alignment:**
- **Secrets Management**: Environment variables for V1 (as per architecture)
- **Network Security**: Isolated Docker network with service name-based communication
- **Data Security**: `.env` file excluded from version control, sensitive data masking in logs

**Monitoring Architecture Alignment:**
- **Structured Logging**: JSON format logging with service identification and request tracing
- **Health Checks**: Docker health checks for all services
- **Log Aggregation**: Docker logs for V1 (centralized logging deferred to future)

---

## Detailed Design

### Services and Modules

| Service/Module | Responsibilities | Inputs | Outputs | Owner |
|----------------|------------------|--------|---------|-------|
| **Project Structure** | Directory organization, `.gitignore`, `.dockerignore` | None | Repository structure | Dev Team |
| **Docker Compose** | Service orchestration, networking, health checks | `docker-compose.yml` | Running containers | Dev Team |
| **Backend Dockerfile** | Backend API container image | `backend/Dockerfile`, `requirements.txt` | `annie-backend` image | Backend Dev |
| **MCP Server Dockerfile** | MCP server container image | `mcp_server/Dockerfile`, MCP SDK | `annie-mcp-server` image | MCP Dev |
| **Telegram Bot Dockerfile** | Telegram bot container image | `telegram_bot/Dockerfile`, python-telegram-bot | `annie-telegram-bot` image | Bot Dev |
| **Redis Service** | State storage container | Redis 7.2 image | Redis instance | Infrastructure |
| **Environment Config** | Variable management, validation | `env.example`, `.env` | Validated config | Dev Team |
| **Logging Module** | Structured logging setup | Log level config | JSON/human-readable logs | Dev Team |
| **Operational Scripts** | Development workflow automation | `run_docker.sh`, `Makefile` | Automated commands | Dev Team |
| **MCP Server Core** | MCP protocol implementation | JSON-RPC 2.0 messages | Tool execution results | MCP Dev |

### Data Models and Contracts

#### Environment Variables Schema

```yaml
# env.example structure
LLM_PROVIDER: "grok-4" | "chatgpt-5"
GROK_API_KEY: string (required if LLM_PROVIDER=grok-4)
CHATGPT_API_KEY: string (required if LLM_PROVIDER=chatgpt-5)
TELEGRAM_BOT_TOKEN: string (required)
BRAVE_SEARCH_API_KEY: string (required)
STOCK_API_KEY: string (required)
AGENTIC_MEMORIES_URL: string (required, e.g., "http://agentic-memories:8000")
REDIS_HOST: string (default: "redis")
REDIS_PORT: integer (default: 6379)
LOG_LEVEL: "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL" (default: "INFO")
BACKEND_PORT: integer (default: 8000)
MCP_SERVER_NAME: string (default: "annie-mcp-server")
```

#### Docker Compose Service Definitions

```yaml
# docker-compose.yml structure
services:
  backend:
    build: ./backend
    ports: ["${BACKEND_PORT:-8000}:8000"]
    environment: [all env vars]
    depends_on: [redis, mcp-server]
    healthcheck: {test: "curl -f http://localhost:8000/health", interval: 30s}
    volumes: ["./backend:/app"]
    networks: [annie-network]
  
  mcp-server:
    build: ./mcp_server
    environment: [tool-specific env vars]
    healthcheck: {test: "docker exec mcp-server python -c 'import mcp; print(\"ok\")'"}
    volumes: ["./mcp_server:/app"]
    networks: [annie-network]
  
  telegram-bot:
    build: ./telegram_bot
    environment: [TELEGRAM_BOT_TOKEN, BACKEND_URL]
    depends_on: [backend]
    volumes: ["./telegram_bot:/app"]
    networks: [annie-network]
  
  redis:
    image: redis:7.2-alpine
    ports: ["6379:6379"]
    healthcheck: {test: "redis-cli ping", interval: 30s}
    volumes: ["redis-data:/data"]
    networks: [annie-network]

networks:
  annie-network:
    driver: bridge

volumes:
  redis-data:
```

#### Logging Data Model

```python
# Structured log format
{
    "timestamp": "2025-11-10T12:00:00Z",
    "service": "backend" | "mcp-server" | "telegram-bot",
    "level": "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL",
    "message": "string",
    "context": {
        "user_id": "string (optional)",
        "conversation_id": "string (optional)",
        "request_id": "string (optional)",
        "tool_name": "string (optional)",
        "execution_time_ms": "number (optional)"
    },
    "error": {
        "code": "string (optional)",
        "message": "string (optional)",
        "stack_trace": "string (optional)"
    }
}
```

#### MCP Server Tool Schema

```json
{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
        "name": "health_check",
        "arguments": {}
    },
    "id": 1
}
```

### APIs and Interfaces

#### Docker Compose API

**Service Definition Interface:**
- **File**: `docker-compose.yml`
- **Format**: YAML
- **Services**: `backend`, `mcp-server`, `telegram-bot`, `redis`
- **Networks**: `annie-network` (bridge driver)
- **Volumes**: Development volumes for hot-reload, Redis data volume

#### Environment Configuration Interface

**File**: `env.example`
- **Format**: Key-value pairs with comments
- **Validation**: Required variables checked on service startup
- **Security**: Sensitive values never logged or exposed

**Script Interface**: `run_docker.sh`
- **Input**: User interaction for `.env` creation
- **Output**: Validated `.env` file, started services
- **Error Handling**: Clear error messages for missing dependencies

#### Makefile Interface

**Commands**:
- `make start` - Start all services
- `make stop` - Stop all services
- `make logs` - View all service logs
- `make logs SERVICE=backend` - View specific service logs
- `make test` - Run test suite
- `make clean` - Clean up containers and volumes

#### MCP Server Interface

**Transport**: Stdio (JSON-RPC 2.0)
**Health Check Tool**:
- **Method**: `tools/call`
- **Tool Name**: `health_check`
- **Parameters**: None
- **Response**: `{"status": "ok", "timestamp": "2025-11-10T12:00:00Z"}`

**Error Response Format**:
```json
{
    "jsonrpc": "2.0",
    "error": {
        "code": -32602,
        "message": "Invalid params"
    },
    "id": 1
}
```

### Workflows and Sequencing

#### Project Setup Workflow

```
1. Developer clones repository
   ↓
2. Developer runs ./run_docker.sh
   ↓
3. Script checks Docker installation
   ↓
4. Script checks Docker Compose availability
   ↓
5. Script checks for .env file
   ↓
6. If .env missing:
   - Script reads env.example
   - Script prompts for required values
   - Script creates .env file
   ↓
7. Script validates .env variables
   ↓
8. Script runs docker-compose up
   ↓
9. Services start in order:
   - Redis (no dependencies)
   - MCP Server (no dependencies)
   - Backend (depends on Redis, MCP Server)
   - Telegram Bot (depends on Backend)
   ↓
10. Health checks validate service readiness
   ↓
11. All services healthy → Development environment ready
```

#### Service Startup Sequence

```
1. Docker Compose reads docker-compose.yml
   ↓
2. Builds images (if needed):
   - backend: Dockerfile.backend → annie-backend:latest
   - mcp-server: Dockerfile.mcp-server → annie-mcp-server:latest
   - telegram-bot: Dockerfile.telegram-bot → annie-telegram-bot:latest
   ↓
3. Creates network: annie-network
   ↓
4. Creates volumes: redis-data
   ↓
5. Starts Redis container
   ↓
6. Starts MCP Server container
   ↓
7. Starts Backend container (waits for Redis, MCP Server healthy)
   ↓
8. Starts Telegram Bot container (waits for Backend healthy)
   ↓
9. Health checks run every 30 seconds
   ↓
10. Services ready for requests
```

#### MCP Tool Call Workflow (Foundation)

```
1. Backend needs to call MCP tool
   ↓
2. Backend constructs JSON-RPC 2.0 message
   ↓
3. Backend executes: docker exec -i annie-mcp-server python -c "..."
   ↓
4. MCP Server receives message via stdio
   ↓
5. MCP Server parses JSON-RPC message
   ↓
6. MCP Server routes to tool handler (health_check)
   ↓
7. Tool executes and returns result
   ↓
8. MCP Server formats JSON-RPC response
   ↓
9. MCP Server writes response to stdout
   ↓
10. Backend reads stdout and parses response
   ↓
11. Backend receives tool result
```

#### Logging Workflow

```
1. Service generates log event
   ↓
2. Logging module formats log:
   - Adds timestamp
   - Adds service name
   - Adds log level
   - Adds context (user_id, request_id, etc.)
   - Masks sensitive data
   ↓
3. Logging module outputs:
   - Development: Human-readable format to stdout
   - Production: JSON format to stdout
   ↓
4. Docker captures stdout/stderr
   ↓
5. Logs available via:
   - docker-compose logs (all services)
   - docker-compose logs SERVICE=backend (specific service)
   - docker logs CONTAINER_ID (direct container logs)
```

---

## Non-Functional Requirements

### Performance

**Service Startup Time:**
- All services start within 30 seconds (p95)
- Health checks pass within 30 seconds of service start
- Docker Compose startup completes within 60 seconds total

**MCP Tool Execution:**
- Health check tool responds within 100ms (p95)
- Tool call via Docker exec completes within 500ms (p95)

**Logging Performance:**
- Logging overhead <1% of request processing time
- Log writes complete within 10ms (p95)

**References:**
- PRD Technical Metrics: MCP Tool Execution <1s average
- Architecture Plan: Tool call flow via Docker exec

### Security

**Secrets Management:**
- API keys and tokens stored in `.env` file (never in code)
- `.env` file excluded from version control (`.gitignore`)
- Sensitive values never logged or exposed in error messages
- Environment variable validation on service startup

**Network Security:**
- Services communicate via isolated Docker network (`annie-network`)
- External access only via exposed ports (Backend API, Redis)
- No direct external access to MCP Server or Telegram Bot

**Data Security:**
- Logs mask sensitive data (API keys, tokens, user personal data)
- Environment variables validated before service startup
- Clear error messages for missing required variables (without exposing values)

**References:**
- Architecture Plan: Secrets Management section
- Architecture Plan: Network Security section

### Reliability/Availability

**Service Availability:**
- All services restart automatically on failure (Docker restart policy)
- Health checks detect service failures within 30 seconds
- Graceful degradation: Services continue if optional dependencies unavailable

**Error Handling:**
- Missing environment variables cause clear error messages and service startup failure
- Docker Compose handles service dependency failures gracefully
- Logging failures don't crash services (fail-safe logging)

**Recovery:**
- Services can be restarted individually without affecting others
- Redis data persists via Docker volume (survives container restarts)
- Development volumes preserve code changes across restarts

**References:**
- PRD: 99%+ uptime requirement
- Architecture Plan: Error Handling Strategy

### Observability

**Logging:**
- Structured logging with JSON format (production) and human-readable format (development)
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL (configurable via LOG_LEVEL env var)
- Log context includes: timestamp, service name, log level, message, context (user_id, conversation_id, request_id)
- Error logs include stack traces, error codes, and relevant context
- Performance logging for slow operations (>1s)

**Health Checks:**
- Docker health checks for all services
- Health check endpoints: `/health` (basic), `/health/detailed` (component health)
- Health check results visible via `docker ps` and `docker inspect`

**Monitoring:**
- Docker logs accessible via `docker-compose logs`
- Service-specific log filtering: `docker-compose logs SERVICE=backend`
- Log aggregation via Docker (centralized logging deferred to future)

**References:**
- Architecture Plan: Monitoring Architecture section
- Architecture Plan: Logging section

---

## Dependencies and Integrations

### External Dependencies

**Docker & Docker Compose:**
- **Docker**: Version 20.10+ (required for containerization)
- **Docker Compose**: Version 2.0+ (required for service orchestration)
- **Purpose**: Containerization and service orchestration
- **Installation**: System-level installation required

**Python Runtime:**
- **Python**: Version 3.12+ (required for all Python services)
- **Purpose**: Backend API, MCP Server, Telegram Bot services
- **Installation**: Via Docker base images

**MCP Python SDK:**
- **Package**: `mcp` (via pip)
- **Version**: Latest stable (to be specified in requirements.txt)
- **Purpose**: MCP protocol implementation
- **Installation**: Via MCP Server Dockerfile

**Redis:**
- **Image**: `redis:7.2-alpine`
- **Purpose**: State storage (sessions, conversation cache)
- **Installation**: Via Docker Compose

**python-telegram-bot:**
- **Package**: `python-telegram-bot` (via pip)
- **Version**: Latest stable (to be specified in requirements.txt)
- **Purpose**: Telegram Bot API integration
- **Installation**: Via Telegram Bot Dockerfile

### Internal Dependencies

**Project Structure:**
- Directory structure must exist before Docker setup
- `.gitignore` and `.dockerignore` must exist before Docker builds

**Environment Configuration:**
- `env.example` must exist before `run_docker.sh` execution
- `.env` file created from `env.example` template

**Docker Compose:**
- All Dockerfiles must exist before `docker-compose up`
- Network and volume definitions in `docker-compose.yml`

**MCP Server:**
- MCP Python SDK must be installed before MCP server starts
- Tool registration happens at server startup

### Integration Points

**Backend ↔ MCP Server:**
- Communication via Docker exec pattern
- JSON-RPC 2.0 protocol over stdio
- Service discovery via Docker Compose service name

**Backend ↔ Redis:**
- Connection via Docker Compose service name (`redis`)
- Redis client library (redis-py) in Backend
- Connection pooling for performance

**Telegram Bot ↔ Backend:**
- HTTP REST API communication
- Service discovery via Docker Compose service name (`backend`)
- Backend URL configured via environment variable

---

## Acceptance Criteria (Authoritative)

### Story 1.1: Project Structure & Repository Setup

1. **AC 1.1.1**: Given a fresh repository, when I check the directory structure, then it includes `backend/`, `mcp_server/`, `telegram_bot/`, `scripts/`, `docs/` directories
2. **AC 1.1.2**: Given the project structure, when I check the repository, then `.gitignore` exists with appropriate exclusions (Python, Docker, IDE files, `.env`, `__pycache__`, `*.pyc`)
3. **AC 1.1.3**: Given the project structure, when I check the repository, then `.dockerignore` exists with appropriate exclusions (`.git`, `docs`, `*.md`, `.env`)
4. **AC 1.1.4**: Given the repository, when I check Python structure, then virtual environment directories are excluded and `requirements.txt` structure is defined
5. **AC 1.1.5**: Given the repository, when I check documentation, then initial `README.md` exists with project overview and setup instructions

### Story 1.2: Docker Compose & Service Configuration

6. **AC 1.2.1**: Given Docker is installed, when I check `docker-compose.yml`, then it defines all services (Backend API, MCP Server, Telegram Bot, Redis)
7. **AC 1.2.2**: Given Docker Compose, when I check service configuration, then each service has proper network configuration and dependencies defined
8. **AC 1.2.3**: Given Docker Compose, when I run `docker-compose up`, then all services start successfully without errors
9. **AC 1.2.4**: Given Docker Compose, when I check health checks, then each service has health check configuration that validates service readiness
10. **AC 1.2.5**: Given Docker Compose, when I check volume mounts, then development volumes are configured for hot-reload capability
11. **AC 1.2.6**: Given Docker Compose, when I check service health, then all services pass their health checks within 30 seconds of startup

### Story 1.3: Environment Configuration & Secrets Management

12. **AC 1.3.1**: Given the project, when I check `env.example`, then it includes all required environment variables with descriptions (LLM API keys, Telegram bot token, Brave Search API key, Stock API key, agentic-memories service URL, Redis configuration, Service ports and URLs)
13. **AC 1.3.2**: Given environment setup, when I run `./run_docker.sh`, then it interactively creates `.env` file from `env.example` if missing
14. **AC 1.3.3**: Given environment variables, when services start, then all required variables are validated and missing variables cause clear error messages
15. **AC 1.3.4**: Given environment variables, when I check security, then sensitive values (API keys, tokens) are never logged or exposed in error messages
16. **AC 1.3.5**: Given environment configuration, when services start, then environment-specific values (dev/staging/prod) can be configured via `.env` file
17. **AC 1.3.6**: Given the `.env` file, when I check `.gitignore`, then `.env` is excluded from version control

### Story 1.4: Logging Infrastructure

18. **AC 1.4.1**: Given any service, when it starts, then structured logging is configured with JSON format (for production) and human-readable format (for development)
19. **AC 1.4.2**: Given logging, when I check log output, then logs include timestamp, service name, log level, message, and context (user_id, conversation_id, request_id)
20. **AC 1.4.3**: Given logging, when errors occur, then error logs include stack traces, error codes, and relevant context for debugging
21. **AC 1.4.4**: Given logging, when I check log levels, then services support configurable log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL) via environment variable
22. **AC 1.4.5**: Given logging, when I check Docker logs, then logs from all services are visible via `docker-compose logs` with service filtering
23. **AC 1.4.6**: Given logging, when sensitive data is logged, then API keys, tokens, and user personal data are masked/redacted in logs
24. **AC 1.4.7**: Given logging, when performance issues occur, then slow operations (>1s) are logged with timing information

### Story 1.5: Operational Scripts & Makefile

25. **AC 1.5.1**: Given the project, when I check `run_docker.sh`, then it checks Docker installation, validates Docker Compose, creates `.env` interactively if missing, verifies dependencies, and starts services
26. **AC 1.5.2**: Given the Makefile, when I run `make start`, then all services start successfully
27. **AC 1.5.3**: Given the Makefile, when I run `make stop`, then all services stop gracefully
28. **AC 1.5.4**: Given the Makefile, when I run `make logs`, then logs from all services are displayed with service names
29. **AC 1.5.5**: Given the Makefile, when I run `make logs SERVICE=backend`, then logs from only the backend service are displayed
30. **AC 1.5.6**: Given the Makefile, when I run `make test`, then test suite runs for all services
31. **AC 1.5.7**: Given the Makefile, when I run `make clean`, then Docker containers, volumes, and temporary files are cleaned up
32. **AC 1.5.8**: Given the scripts, when I check execution, then scripts have proper error handling and informative error messages

### Story 1.6: MCP Server Foundation

33. **AC 1.6.1**: Given the MCP server Dockerfile, when I build the image, then it includes MCP Python SDK (`pip install mcp`) and all tool dependencies
34. **AC 1.6.2**: Given the MCP server, when it starts, then it initializes stdio transport and listens for JSON-RPC 2.0 messages
35. **AC 1.6.3**: Given the MCP server is running, when I call the health check tool via Docker exec, then it responds with `{"status": "ok", "timestamp": "..."}`
36. **AC 1.6.4**: Given the MCP server, when I execute a tool call via Docker exec pattern, then the tool executes and returns results via stdio
37. **AC 1.6.5**: Given the MCP server, when I check logs, then structured logging is visible with tool call information (tool name, parameters, execution time, results)
38. **AC 1.6.6**: Given the MCP server, when an invalid tool call is made, then it returns a proper JSON-RPC error response with error code and message

---

## Traceability Mapping

| AC ID | Spec Section | Component/API | Test Idea |
|-------|--------------|---------------|-----------|
| AC 1.1.1 | Project Structure | Directory structure | Verify all directories exist |
| AC 1.1.2 | Project Structure | `.gitignore` | Check exclusions are present |
| AC 1.1.3 | Project Structure | `.dockerignore` | Check exclusions are present |
| AC 1.1.4 | Project Structure | Python structure | Verify virtualenv exclusion |
| AC 1.1.5 | Project Structure | `README.md` | Verify file exists with content |
| AC 1.2.1 | Docker Compose | `docker-compose.yml` | Verify all services defined |
| AC 1.2.2 | Docker Compose | Service configuration | Check network and dependencies |
| AC 1.2.3 | Docker Compose | Service startup | Run `docker-compose up` and verify |
| AC 1.2.4 | Docker Compose | Health checks | Verify health check configs |
| AC 1.2.5 | Docker Compose | Volume mounts | Check volume mount configs |
| AC 1.2.6 | Docker Compose | Service health | Verify health checks pass |
| AC 1.3.1 | Environment Config | `env.example` | Verify all required vars present |
| AC 1.3.2 | Environment Config | `run_docker.sh` | Test interactive `.env` creation |
| AC 1.3.3 | Environment Config | Service startup | Test missing var validation |
| AC 1.3.4 | Environment Config | Logging | Verify sensitive data masking |
| AC 1.3.5 | Environment Config | Service config | Test env-specific values |
| AC 1.3.6 | Environment Config | `.gitignore` | Verify `.env` exclusion |
| AC 1.4.1 | Logging | Logging module | Verify format configuration |
| AC 1.4.2 | Logging | Log output | Check log structure |
| AC 1.4.3 | Logging | Error logs | Verify error context |
| AC 1.4.4 | Logging | Log levels | Test LOG_LEVEL env var |
| AC 1.4.5 | Logging | Docker logs | Test log filtering |
| AC 1.4.6 | Logging | Data masking | Test sensitive data redaction |
| AC 1.4.7 | Logging | Performance logs | Test slow operation logging |
| AC 1.5.1 | Operational Scripts | `run_docker.sh` | Test script functionality |
| AC 1.5.2 | Operational Scripts | Makefile | Test `make start` |
| AC 1.5.3 | Operational Scripts | Makefile | Test `make stop` |
| AC 1.5.4 | Operational Scripts | Makefile | Test `make logs` |
| AC 1.5.5 | Operational Scripts | Makefile | Test service filtering |
| AC 1.5.6 | Operational Scripts | Makefile | Test `make test` |
| AC 1.5.7 | Operational Scripts | Makefile | Test `make clean` |
| AC 1.5.8 | Operational Scripts | Scripts | Test error handling |
| AC 1.6.1 | MCP Server | Dockerfile | Verify MCP SDK installation |
| AC 1.6.2 | MCP Server | Server initialization | Verify stdio transport |
| AC 1.6.3 | MCP Server | Health check tool | Test tool call via Docker exec |
| AC 1.6.4 | MCP Server | Tool execution | Test tool call workflow |
| AC 1.6.5 | MCP Server | Logging | Verify tool call logging |
| AC 1.6.6 | MCP Server | Error handling | Test invalid tool call |

---

## Risks, Assumptions, Open Questions

### Risks

**R1: Docker Setup Complexity**
- **Description**: Docker Compose configuration may be complex with multiple services and dependencies
- **Impact**: High - Blocks all development work
- **Probability**: Medium
- **Mitigation**: Start with simple configuration, iterate, document issues, test frequently
- **Owner**: Dev Team

**R2: Environment Configuration Errors**
- **Description**: Missing or incorrect environment variables may cause service failures
- **Impact**: High - Services won't start
- **Probability**: Medium
- **Mitigation**: Comprehensive `env.example`, validation on startup, clear error messages
- **Owner**: Dev Team

**R3: MCP Server Docker Exec Pattern**
- **Description**: Docker exec pattern for MCP communication may have performance or reliability issues
- **Impact**: Medium - Affects tool calling performance
- **Probability**: Low
- **Mitigation**: Test early, optimize if needed, consider HTTP bridge for future
- **Owner**: MCP Dev

**R4: Service Startup Dependencies**
- **Description**: Service startup order and health check timing may cause race conditions
- **Impact**: Medium - Services may fail to start correctly
- **Probability**: Low
- **Mitigation**: Use Docker Compose `depends_on` with health checks, test startup sequence
- **Owner**: Dev Team

### Assumptions

**A1: Docker Availability**
- **Assumption**: Developers have Docker and Docker Compose installed
- **Validation**: `run_docker.sh` checks Docker installation
- **Impact**: High - Required for development

**A2: Python 3.12+ Availability**
- **Assumption**: Python 3.12+ is available via Docker base images
- **Validation**: Dockerfile base images specify Python version
- **Impact**: High - Required for all Python services

**A3: MCP Python SDK Availability**
- **Assumption**: MCP Python SDK is available via pip
- **Validation**: MCP Server Dockerfile installs SDK
- **Impact**: High - Required for MCP server

**A4: Redis Image Availability**
- **Assumption**: Redis 7.2-alpine image is available on Docker Hub
- **Validation**: Docker Compose pulls image on startup
- **Impact**: High - Required for state management

### Open Questions

**Q1: MCP Server Performance**
- **Question**: Will Docker exec pattern provide sufficient performance for tool calls?
- **Next Step**: Benchmark tool call performance, consider HTTP bridge if needed
- **Owner**: MCP Dev

**Q2: Log Aggregation Strategy**
- **Question**: Should we implement centralized logging in V1 or defer to future?
- **Decision**: Defer to future (use Docker logs for V1)
- **Owner**: Dev Team

**Q3: Development vs Production Configs**
- **Question**: How should we handle different configurations for dev/staging/prod?
- **Decision**: Use `.env` file with environment-specific values for V1
- **Owner**: Dev Team

---

## Test Strategy Summary

### Test Levels

**Unit Tests:**
- **Scope**: Individual components (logging module, environment validation, script functions)
- **Framework**: pytest (Python), shell script testing
- **Coverage Target**: 80%+ for new code
- **Focus**: Logging format, environment validation, script error handling

**Integration Tests:**
- **Scope**: Service interactions (Docker Compose startup, health checks, MCP tool calls)
- **Framework**: Docker Compose test containers, pytest with Docker fixtures
- **Coverage Target**: Critical paths (service startup, health checks, tool calls)
- **Focus**: Service startup sequence, health check validation, MCP tool execution

**System Tests:**
- **Scope**: End-to-end workflows (project setup, service startup, operational scripts)
- **Framework**: Manual testing, automated scripts
- **Coverage Target**: All acceptance criteria
- **Focus**: Complete setup workflow, service health, script functionality

### Test Scenarios

**Project Setup Tests:**
- Fresh repository setup
- Directory structure creation
- `.gitignore` and `.dockerignore` validation
- `README.md` content verification

**Docker Compose Tests:**
- Service definition validation
- Network and volume creation
- Service startup sequence
- Health check execution
- Service dependency resolution

**Environment Configuration Tests:**
- `env.example` completeness
- `.env` file creation workflow
- Environment variable validation
- Sensitive data masking
- Missing variable error handling

**Logging Tests:**
- Log format validation (JSON vs human-readable)
- Log level configuration
- Context inclusion (user_id, request_id)
- Sensitive data masking
- Performance logging (>1s operations)
- Docker log aggregation

**Operational Scripts Tests:**
- `run_docker.sh` functionality
- Makefile command execution
- Error handling and error messages
- Service-specific log filtering

**MCP Server Tests:**
- MCP SDK installation
- Stdio transport initialization
- Health check tool execution
- Tool call workflow
- Error handling (invalid tool calls)
- Logging integration

### Test Data

**Environment Variables:**
- Valid configuration (all required vars present)
- Missing required variables
- Invalid variable values
- Sensitive data (API keys, tokens)

**Docker Scenarios:**
- Fresh Docker environment
- Existing containers
- Network conflicts
- Volume conflicts

**MCP Tool Calls:**
- Valid health check tool call
- Invalid tool name
- Invalid parameters
- Service unavailable

### Test Execution

**Automated Tests:**
- Unit tests run via `make test`
- Integration tests run in CI/CD (future)
- Docker Compose tests run locally

**Manual Tests:**
- Complete setup workflow
- Service startup verification
- Operational script testing
- MCP tool call testing

---

_This technical specification provides the foundation for implementing Epic 1: Foundation & Infrastructure. All stories within this epic should reference this document for technical context and implementation guidance._
