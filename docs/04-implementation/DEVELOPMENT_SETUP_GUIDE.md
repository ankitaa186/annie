# Development Setup Guide

## Overview

This guide walks through setting up a local development environment for Annie chatbot.

## Prerequisites

### Required Software

- **Docker Desktop** 4.20+ ([Download](https://www.docker.com/products/docker-desktop))
- **Python** 3.12+ ([Download](https://www.python.org/downloads/))
- **Git** 2.40+ ([Download](https://git-scm.com/downloads))
- **Code Editor** (VS Code recommended)

### Optional Tools

- **Postman** - API testing ([Download](https://www.postman.com/downloads/))
- **Docker Compose** V2 (included in Docker Desktop)
- **Make** - Command shortcuts (pre-installed on macOS/Linux)

### API Keys

Before starting, obtain:
- **XAI API Key** - Grok-4 ([x.ai](https://x.ai))
- **Telegram Bot Token** - From @BotFather
- **Brave Search API Key** - Optional ([brave.com/search/api](https://brave.com/search/api))
- **OpenAI API Key** - Optional fallback ([platform.openai.com](https://platform.openai.com))

## Initial Setup

### 1. Clone Repository

```bash
# Clone the repository
git clone https://github.com/yourusername/annie.git
cd annie

# Verify structure
ls -la
# Should see: backend/, mcp_server/, telegram_bot/, docs/, etc.
```

### 2. Set Up agentic-memories

Annie depends on the agentic-memories service.

```bash
# Navigate to agentic-memories
cd ~/dev/agentic-memories

# Start the service
./run_docker.sh
# Follow prompts to create .env

# Verify it's running
curl http://localhost:8080/health
# Should return: {"status":"ok",...}

# View logs
make logs

# Return to Annie directory
cd ~/dev/annie
```

### 3. Configure Environment

```bash
# Copy environment template
cp env.example .env

# Edit .env with your API keys
nano .env  # or use your preferred editor
```

**Required Configuration**:
```bash
# LLM Configuration
XAI_API_KEY=your-xai-key-here
TELEGRAM_BOT_TOKEN=your-telegram-token-here

# Optional
OPENAI_API_KEY=your-openai-key-here
BRAVE_API_KEY=your-brave-key-here

# Services (defaults are usually fine)
AGENTIC_MEMORIES_URL=http://host.docker.internal:8080
LLM_PROVIDER=grok4
LOG_LEVEL=DEBUG  # Use DEBUG for development
```

**Save and secure**:
```bash
chmod 600 .env
```

### 4. Verify Prerequisites

```bash
# Check Docker
docker --version
# Should show: Docker version 24.0.0 or higher

# Check Docker is running
docker info
# Should show system info

# Check Python
python --version
# Should show: Python 3.12.0 or higher

# Check Make (optional)
make --version
```

## Development Workflow

### Option A: Full Docker Development (Recommended)

**Start Services**:
```bash
# Start all services
./run_docker.sh
# Or: make start

# View logs
make logs

# View specific service logs
make logs-backend
make logs-mcp
make logs-telegram
```

**Code Changes**:
- Code mounted as volumes
- Changes reflected immediately (hot reload)
- No need to rebuild for code changes

**Rebuild** (when changing dependencies):
```bash
make rebuild
```

**Stop Services**:
```bash
make stop
# Or: docker compose down
```

### Option B: Hybrid Development

Run some services locally for faster iteration:

**Backend Locally**:
```bash
# Terminal 1: Start dependencies only
docker compose up -d redis mcp-server

# Terminal 2: Run backend locally
cd backend
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000

# Terminal 3: Run Telegram bot locally
cd telegram_bot
pip install -r requirements.txt
python bot.py
```

**Advantages**:
- Faster Python debugging
- Direct access to logs
- Better IDE integration

**Disadvantages**:
- Must manage Python environments
- More manual setup

## Project Structure

```
annie/
├── backend/                    # Backend API service
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py            # FastAPI app
│   │   ├── routes/            # API routes
│   │   └── models/            # Data models
│   ├── core/
│   │   ├── llm_client.py      # LLM integration
│   │   ├── mcp_client.py      # MCP communication
│   │   └── state_manager.py  # State management
│   ├── requirements.txt
│   └── tests/
├── mcp_server/                # MCP Server
│   ├── server.py              # MCP server main
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── internet_access.py
│   │   └── memories.py
│   ├── requirements.txt
│   └── tests/
├── telegram_bot/              # Telegram Bot
│   ├── bot.py                 # Bot main
│   ├── handlers/              # Message handlers
│   ├── requirements.txt
│   └── tests/
├── scripts/                   # Utility scripts
├── docs/                      # Documentation
├── tests/                     # Integration tests
├── docker-compose.yml         # Service orchestration
├── Dockerfile.backend         # Backend container
├── Dockerfile.mcp-server      # MCP server container
├── Dockerfile.telegram-bot    # Telegram bot container
├── run_docker.sh              # Main startup script
├── Makefile                   # Common commands
├── env.example                # Environment template
└── README.md                  # Project overview
```

## Common Development Tasks

### Running Tests

```bash
# All tests
make test

# Unit tests only
make test-unit

# Integration tests
make test-integration

# E2E tests (requires services running)
make test-e2e

# Specific test file
pytest tests/test_backend.py -v

# With coverage
pytest --cov=backend tests/
```

### Viewing Logs

```bash
# All services
make logs

# Specific service
make logs-backend
make logs-mcp
make logs-telegram

# Follow logs
docker compose logs -f backend

# Last 100 lines
docker compose logs --tail=100 backend
```

### Database Access

**Redis**:
```bash
# Connect to Redis
docker exec -it annie-redis redis-cli

# View all keys
KEYS *

# Get value
GET user:123:session:telegram

# Exit
exit
```

**PostgreSQL** (Future):
```bash
# Connect to PostgreSQL
docker exec -it annie-postgres psql -U annie

# List tables
\dt

# Query
SELECT * FROM conversations LIMIT 10;

# Exit
\q
```

### API Testing

**Using curl**:
```bash
# Health check
curl http://localhost:8000/health

# Send chat message
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "dev_user",
    "platform": "test",
    "message": "Hello!"
  }'
```

**Using Postman**:
1. Import collection: `docs/03-technical/Annie_API.postman_collection.json`
2. Set base URL: `http://localhost:8000`
3. Run requests

**Using Python**:
```python
import httpx
import asyncio

async def test_chat():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/v1/chat",
            json={
                "user_id": "dev_user",
                "platform": "test",
                "message": "Hello!"
            }
        )
        print(response.json())

asyncio.run(test_chat())
```

### Debugging

**Backend** (Python Debugger):
```python
# Add breakpoint
import pdb; pdb.set_trace()

# Or use VS Code debugger
# Create .vscode/launch.json
```

**Docker Logs**:
```bash
# Real-time logs
docker compose logs -f backend

# Error logs only
docker compose logs backend | grep ERROR
```

**MCP Server**:
```bash
# Test MCP tool directly
docker exec -it annie-mcp-server python -c "
from tools.internet_access import InternetAccessTool
import asyncio

async def test():
    tool = InternetAccessTool()
    result = await tool.search('Python programming')
    print(result)

asyncio.run(test())
"
```

## IDE Setup

### VS Code

**Extensions**:
- Python (ms-python.python)
- Docker (ms-azuretools.vscode-docker)
- Pylance (ms-python.vscode-pylance)
- REST Client (humao.rest-client)

**Settings** (`.vscode/settings.json`):
```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/venv/bin/python",
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": true,
  "python.formatting.provider": "black",
  "python.testing.pytestEnabled": true,
  "files.exclude": {
    "**/__pycache__": true,
    "**/*.pyc": true
  }
}
```

**Launch Configuration** (`.vscode/launch.json`):
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: Backend",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": [
        "backend.api.main:app",
        "--reload",
        "--port",
        "8000"
      ],
      "envFile": "${workspaceFolder}/.env"
    }
  ]
}
```

### PyCharm

**Setup**:
1. Open Project
2. Configure Python Interpreter (3.12+)
3. Install requirements
4. Configure Docker integration
5. Set up pytest runner

## Troubleshooting

### Docker Issues

**Issue**: Docker daemon not running
```bash
# Solution: Start Docker Desktop
open -a Docker  # macOS
```

**Issue**: Port already in use
```bash
# Find process using port
lsof -i :8000

# Kill process
kill -9 <PID>

# Or change port in docker-compose.yml
```

**Issue**: Container won't start
```bash
# Check logs
docker compose logs backend

# Remove old containers
docker compose down -v
docker compose up -d
```

### Python Issues

**Issue**: Module not found
```bash
# Reinstall dependencies
pip install -r requirements.txt

# Or rebuild Docker image
docker compose build backend
```

**Issue**: Import errors
```bash
# Check PYTHONPATH
export PYTHONPATH=/app

# Or add to .env
PYTHONPATH=/app
```

### agentic-memories Issues

**Issue**: Connection refused
```bash
# Check service is running
curl http://localhost:8080/health

# Restart service
cd ~/dev/agentic-memories
make restart

# Check Docker network
docker network inspect bridge
```

**Issue**: Slow responses
```bash
# Check agentic-memories logs
cd ~/dev/agentic-memories
make logs

# Check resource usage
docker stats
```

## Development Best Practices

### Code Style

- Follow PEP 8
- Use Black for formatting
- Use Pylint for linting
- Type hints for all functions
- Docstrings for all classes/functions

**Format code**:
```bash
# Format all Python files
black .

# Check linting
pylint backend/
```

### Git Workflow

```bash
# Create feature branch
git checkout -b feature/new-feature

# Make changes
# ... edit files ...

# Commit changes
git add .
git commit -m "feat: add new feature"

# Push to remote
git push origin feature/new-feature

# Create pull request
```

### Testing Workflow

1. Write test first (TDD)
2. Implement feature
3. Run tests locally
4. Fix failures
5. Commit

### Environment Management

- Never commit `.env`
- Use `.env.example` as template
- Document all new environment variables
- Keep secrets secure

## Next Steps

1. **Explore Documentation**: Read [`docs/README.md`](../README.md)
2. **Review Architecture**: See [`ARCHITECTURE_PLAN.md`](../02-architecture/ARCHITECTURE_PLAN.md)
3. **Follow Implementation Plan**: See [`V1_IMPLEMENTATION_PLAN.md`](./V1_IMPLEMENTATION_PLAN.md)
4. **Start Contributing**: See [`CONTRIBUTING.md`](../../CONTRIBUTING.md)

## Getting Help

### Resources

- **Documentation**: `docs/`
- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions

### Common Commands Reference

```bash
# Start services
make start

# Stop services
make stop

# View logs
make logs

# Run tests
make test

# Clean up
make clean

# Rebuild
make rebuild

# Help
make help
```

## Appendix

### Useful Docker Commands

```bash
# List running containers
docker ps

# List all containers
docker ps -a

# Remove stopped containers
docker compose rm

# Rebuild specific service
docker compose build backend

# Shell into container
docker exec -it annie-backend bash

# View container logs
docker logs annie-backend

# Restart service
docker compose restart backend
```

### Useful Python Commands

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate      # Windows

# Install dependencies
pip install -r requirements.txt

# Freeze dependencies
pip freeze > requirements.txt

# Run Python file
python backend/api/main.py

# Run with debugger
python -m pdb backend/api/main.py
```

