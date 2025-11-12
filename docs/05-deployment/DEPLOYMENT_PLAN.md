# Deployment & Operations Plan

## Overview

This document outlines the deployment and operations plan for Annie chatbot, covering Docker deployment, operational scripts, monitoring, and production considerations.

## Docker Deployment Architecture

### Service Composition

**Services**:
1. **redis** - State management and caching
2. **mcp-server** - MCP Server container
3. **backend** - Backend API container
4. **telegram-bot** - Telegram Bot container

### Docker Compose Structure

```yaml
version: '3.8'

services:
  redis:
    image: redis:7.2-alpine
    container_name: annie-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - annie-network
    restart: unless-stopped

  mcp-server:
    build:
      context: .
      dockerfile: Dockerfile.mcp-server
    image: annie-mcp-server:local
    container_name: annie-mcp-server
    extra_hosts:
      - "host.docker.internal:host-gateway"
    environment:
      - BRAVE_API_KEY=${BRAVE_API_KEY}
      - AGENTIC_MEMORIES_URL=${AGENTIC_MEMORIES_URL:-http://host.docker.internal:8080}
      - PYTHONUNBUFFERED=1
    volumes:
      - ./tools:/app/tools:ro
      - ./mcp_server:/app/mcp_server:ro
    depends_on:
      redis:
        condition: service_healthy
    networks:
      - annie-network
    restart: unless-stopped
    stdin_open: true
    tty: true

  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    image: annie-backend:local
    container_name: annie-backend
    extra_hosts:
      - "host.docker.internal:host-gateway"
    ports:
      - "8000:8000"
    environment:
      - LLM_PROVIDER=${LLM_PROVIDER:-grok4}
      - XAI_API_KEY=${XAI_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - REDIS_URL=redis://redis:6379/0
      - MCP_SERVER_CONTAINER=annie-mcp-server
      - AGENTIC_MEMORIES_URL=${AGENTIC_MEMORIES_URL:-http://host.docker.internal:8080}
      - PYTHONUNBUFFERED=1
    volumes:
      - ./backend:/app/backend:ro
    depends_on:
      - redis
      - mcp-server
    networks:
      - annie-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

  telegram-bot:
    build:
      context: .
      dockerfile: Dockerfile.telegram-bot
    image: annie-telegram-bot:local
    container_name: annie-telegram-bot
    environment:
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - BACKEND_API_URL=http://backend:8000
      - PYTHONUNBUFFERED=1
    volumes:
      - ./telegram_bot:/app/telegram_bot:ro
    depends_on:
      backend:
        condition: service_healthy
    networks:
      - annie-network
    restart: unless-stopped

volumes:
  redis_data:
    driver: local

networks:
  annie-network:
    driver: bridge
```

## Operational Scripts

### run_docker.sh

**Purpose**: Main startup script following agentic-memories pattern

**Features**:
- Docker availability check
- Interactive `.env` creation
- External dependency verification
- Service startup
- Helpful output

**Key Sections**:
1. Docker detection and validation
2. Docker compose command detection
3. Interactive `.env` creation
4. Environment loading
5. Dependency verification (agentic-memories)
6. Service startup
7. Status output

### Makefile

**Purpose**: Common operational commands

**Commands**:
- `make help` - Show help
- `make start` - Start services
- `make stop` - Stop services
- `make logs` - View logs
- `make logs-backend` - View backend logs
- `make logs-mcp` - View MCP server logs
- `make logs-telegram` - View Telegram bot logs
- `make clean` - Clean up
- `make rebuild` - Rebuild containers
- `make restart` - Restart services
- `make health` - Check health
- `make dev` - Development mode

## Environment Management

### Environment Variables

**Required**:
- `XAI_API_KEY` - Grok-4 API key
- `TELEGRAM_BOT_TOKEN` - Telegram bot token

**Optional**:
- `OPENAI_API_KEY` - ChatGPT-5 fallback
- `BRAVE_API_KEY` - Brave Search API key
- `AGENTIC_MEMORIES_URL` - agentic-memories URL (default: http://host.docker.internal:8080)
- `LLM_PROVIDER` - Primary LLM (default: grok4)
- `LOG_LEVEL` - Logging level (default: INFO)

### env.example Template

```bash
# LLM Configuration
LLM_PROVIDER=grok4
XAI_API_KEY=xaikey-REPLACE_ME
OPENAI_API_KEY=sk-REPLACE_ME

# Telegram Bot
TELEGRAM_BOT_TOKEN=REPLACE_ME

# Internet Access
BRAVE_API_KEY=REPLACE_ME

# Agentic Memories (external service)
AGENTIC_MEMORIES_URL=http://host.docker.internal:8080

# Backend Configuration
LOG_LEVEL=INFO
REDIS_URL=redis://redis:6379/0
```

## Health Checks

### Health Check Endpoints

**Backend API**:
- `GET /health` - Basic health check
- Returns: `{"status": "ok", "checks": {...}}`

**Health Check Components**:
- MCP server connectivity
- Redis connectivity
- LLM API connectivity
- agentic-memories service connectivity

### Docker Health Checks

**All Services**:
- Redis: `redis-cli ping`
- Backend: `curl -f http://localhost:8000/health`
- MCP Server: Via backend health check
- Telegram Bot: Process running check

## Logging Strategy

### Structured Logging

**Format**: JSON

**Fields**:
- `timestamp` - ISO 8601 timestamp
- `level` - Log level (DEBUG, INFO, WARNING, ERROR)
- `service` - Service name
- `message` - Log message
- `user_id` - User ID (if applicable)
- `request_id` - Request ID for tracing

### Log Levels

- `DEBUG` - Detailed debugging (development only)
- `INFO` - General information
- `WARNING` - Warning messages
- `ERROR` - Error messages
- `CRITICAL` - Critical errors

### Log Aggregation

**V1**: Docker logs
**Future**: Centralized logging (ELK, Loki, etc.)

## Monitoring Strategy

### Key Metrics

**Performance Metrics**:
- Request rate (requests/second)
- Response latency (p50, p95, p99)
- Error rate (errors/second)
- Tool call success rate

**Resource Metrics**:
- CPU usage
- Memory usage
- Network I/O
- Disk I/O

**Business Metrics**:
- Active users
- Messages per user
- Tool usage statistics
- Token usage

### Monitoring Implementation

**V1**: Basic metrics endpoint
**Future**: Prometheus + Grafana

## Production Deployment

### Pre-Production Checklist

- [ ] All environment variables configured
- [ ] Secrets stored securely
- [ ] Health checks passing
- [ ] Logging configured
- [ ] Monitoring setup
- [ ] Backup strategy defined
- [ ] Security hardening applied
- [ ] Load testing completed
- [ ] Documentation complete

### Production Configuration

**Differences from Development**:
- Code copied into images (not volumes)
- Production logging level
- Resource limits set
- Health checks enabled
- Restart policies configured
- Secrets from external source

### Scaling Strategy

**Horizontal Scaling**:
- Backend API: Scale to 3+ instances
- Load balancer required
- Shared Redis for state

**Vertical Scaling**:
- Increase container resources
- Monitor and adjust based on usage

## Cost Management

### Cost Tracking

**Track**:
- LLM API token usage
- Infrastructure costs
- External API costs

**Implementation**:
- Token usage tracking in Redis
- Cost calculation based on usage
- Budget alerts

### Cost Optimization

**Strategies**:
- Response caching
- Token optimization
- Right-sized infrastructure
- Reserved instances (production)

## Disaster Recovery

### Backup Strategy

**Redis**:
- RDB snapshots
- AOF persistence
- Daily backups

**PostgreSQL** (Future):
- Daily database backups
- Point-in-time recovery
- Backup retention: 30 days

### Recovery Procedures

**Service Recovery**:
- Automatic restart via Docker
- Health check-based recovery
- Manual intervention if needed

**Data Recovery**:
- Restore from backups
- Verify data integrity
- Test recovery procedures

## Security Considerations

### Container Security

- Non-root users in containers
- Minimal base images
- Image vulnerability scanning
- Secrets not in images

### Network Security

- Isolated Docker network
- Limited port exposure
- HTTPS for external APIs
- Rate limiting

### Application Security

- Input validation
- SQL injection prevention
- XSS prevention
- CSRF protection
- Secure headers

## Troubleshooting Guide

### Common Issues

1. **Services won't start**
   - Check Docker daemon running
   - Verify `.env` file exists
   - Check logs: `make logs`

2. **MCP Server communication fails**
   - Verify MCP server container running
   - Check Docker exec permissions
   - Review MCP server logs

3. **LLM API errors**
   - Verify API keys configured
   - Check rate limits
   - Review fallback configuration

4. **agentic-memories connection fails**
   - Verify service running
   - Check URL configuration
   - Review network connectivity

## References

- OPERATIONAL_PATTERNS_RESEARCH.md: Operational patterns
- PRODUCTION_DEPLOYMENT_RESEARCH.md: Production deployment
- COST_ANALYSIS_RESEARCH.md: Cost analysis
- DOCKER_ARCHITECTURE_RESEARCH.md: Docker architecture

