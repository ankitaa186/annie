# Annie Makefile
# Development commands for managing Annie services

.PHONY: help setup install venv test test-unit test-integration test-backend test-mcp test-telegram coverage start stop logs clean clean-venv clean-all rebuild restart health shell check-loki lint format format-check gh gh-read gh-diff gh-write gh-update terminal-start terminal-stop terminal-logs

# Detect Docker Compose command (v2 or v1)
COMPOSE_CMD := $(shell if docker compose version >/dev/null 2>&1; then echo "docker compose"; else echo "docker-compose"; fi)

# Read ENVIRONMENT from .env if ENV not set on command line
# Priority: ENV from command line > ENVIRONMENT from .env > default "dev"
ENV ?= $(shell grep -E '^ENVIRONMENT=' .env 2>/dev/null | cut -d'=' -f2 || echo "dev")

# Compose file selection based on ENV (dev or prod)
# Production mode uses Loki logging via docker-compose.prod.yml
COMPOSE_FILES = $(if $(filter prod,$(ENV)),-f docker-compose.yml -f docker-compose.prod.yml,)

# Detect uv or fallback to pip
UV_AVAILABLE := $(shell command -v uv 2>/dev/null)
PYTHON_VERSION := 3.12

# Activate venv for all test commands
VENV := . .venv/bin/activate &&

# Default target
help: ## Show this help message
	@echo "Annie Development Commands"
	@echo "=========================="
	@echo ""
	@echo "  Environment: Use ENV=prod for production mode (e.g., make start ENV=prod)"
	@echo ""
	@echo "  Setup:"
	@grep -E '^(setup|install|start|stop|clean|clean-venv|clean-all):.*## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "    \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  Code Quality:"
	@grep -E '^(lint|format|format-check):.*## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "    \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  Testing:"
	@grep -E '^(test[a-zA-Z0-9_-]*|coverage):.*## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "    \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  Docker:"
	@grep -E '^(logs|rebuild|restart|health|shell):.*## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "    \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  Host Terminal:"
	@grep -E '^terminal[a-zA-Z0-9_-]*:.*## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "    \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  GitHub (use ENV=prod for production):"
	@grep -E '^gh[a-zA-Z0-9_-]*:.*## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "    \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ============================================================
# SETUP
# ============================================================

setup: ## Interactive first-boot setup wizard (creates .env, checks services)
	@bash ./scripts/setup.sh

# Ensure venv exists and dependencies are installed
.venv/bin/activate: backend/requirements.txt mcp_server/requirements.txt telegram_bot/requirements.txt
ifdef UV_AVAILABLE
	@if [ ! -d ".venv" ]; then \
		echo "Creating virtual environment with uv (Python $(PYTHON_VERSION))..."; \
		uv venv --python $(PYTHON_VERSION); \
	fi
	@echo "Installing dependencies with uv..."
	@uv pip install -q -r backend/requirements.txt -r mcp_server/requirements.txt -r telegram_bot/requirements.txt
else
	@echo "uv not found, using pip (install uv for faster installs: curl -LsSf https://astral.sh/uv/install.sh | sh)"
	@if [ ! -d ".venv" ]; then \
		echo "Creating virtual environment..."; \
		python$(PYTHON_VERSION) -m venv .venv || python3 -m venv .venv; \
	fi
	@echo "Installing dependencies..."
	@$(VENV) pip install --upgrade pip -q
	@$(VENV) pip install -q -r backend/requirements.txt
	@$(VENV) pip install -q -r mcp_server/requirements.txt
	@$(VENV) pip install -q -r telegram_bot/requirements.txt
endif
	@touch .venv/bin/activate

venv: .venv/bin/activate ## Setup venv and install all dependencies

install: venv ## Setup venv and install dependencies
	@echo "Dependencies installed in .venv/"

start: ## Start all Docker services
	@echo "Starting Annie services..."
	@./scripts/run_docker.sh

stop: ## Stop all Docker services (use ENV=prod for production)
	@echo "Stopping Annie services..."
	@$(COMPOSE_CMD) $(COMPOSE_FILES) down
	@echo "Services stopped."
	@echo "Note: host-terminal-mcp is a separate host tool — manage with 'make terminal-stop' if needed."

clean: ## Clean up Docker resources and caches
	@echo "Cleaning up Docker resources..."
	@$(COMPOSE_CMD) down -v --remove-orphans
	@echo "Removing build artifacts..."
	@find . -type d -name "__pycache__" -exec rm -r {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -r {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -r {} + 2>/dev/null || true
	@echo "Cleanup complete."

clean-venv: ## Remove virtual environment
	@echo "Removing virtual environment..."
	@rm -rf .venv
	@echo "Virtual environment removed."

clean-all: clean clean-venv ## Full cleanup (Docker + venv + caches)

# ============================================================
# CODE QUALITY
# ============================================================

lint: venv ## Run linters (ruff). Use FIX=1 to auto-fix
	$(VENV) pip install -q ruff
ifdef FIX
	$(VENV) ruff check --fix backend/ mcp_server/ telegram_bot/
else
	$(VENV) ruff check backend/ mcp_server/ telegram_bot/
endif

format: venv ## Check formatting (ruff). Use FIX=1 to apply fixes
	$(VENV) pip install -q ruff
ifdef FIX
	$(VENV) ruff format backend/ mcp_server/ telegram_bot/
else
	$(VENV) ruff format --check backend/ mcp_server/ telegram_bot/
endif

# ============================================================
# TESTING - All Services
# ============================================================

test: venv ## Run all tests (unit + integration, excludes e2e)
	$(VENV) pytest backend/tests mcp_server/tests telegram_bot/tests -v --ignore=backend/tests/e2e --ignore=mcp_server/tests/e2e --ignore=telegram_bot/tests/e2e $(PYTEST_ARGS)

test-unit: venv ## Run unit tests only
	$(VENV) pytest backend/tests/unit mcp_server/tests telegram_bot/tests/unit -v $(PYTEST_ARGS)

test-integration: venv ## Run integration tests only (excludes e2e)
	$(VENV) pytest backend/tests/integration telegram_bot/tests/integration -v $(PYTEST_ARGS)

test-all: venv ## Run ALL tests including e2e
	$(VENV) pytest backend/tests mcp_server/tests telegram_bot/tests -v --ignore="" $(PYTEST_ARGS)

coverage: venv ## Run tests with coverage (excludes e2e)
	$(VENV) pip install -q pytest-cov
	$(VENV) pytest backend/tests mcp_server/tests telegram_bot/tests --ignore=backend/tests/e2e --ignore=mcp_server/tests/e2e --ignore=telegram_bot/tests/e2e --cov=backend/api --cov=mcp_server --cov=telegram_bot --cov-report=term-missing --cov-report=html $(PYTEST_ARGS)
	@echo "HTML coverage report: htmlcov/index.html"

# ============================================================
# TESTING - Individual Services
# ============================================================

test-backend: venv ## Run backend tests (excluding e2e)
	$(VENV) pytest backend/tests -v --ignore=backend/tests/e2e $(PYTEST_ARGS)

test-mcp: venv ## Run MCP server tests (excluding e2e)
	$(VENV) pytest mcp_server/tests -v --ignore=mcp_server/tests/e2e $(PYTEST_ARGS)

test-telegram: venv ## Run Telegram bot tests (excluding e2e)
	$(VENV) pytest telegram_bot/tests -v --ignore=telegram_bot/tests/e2e $(PYTEST_ARGS)

# ============================================================
# E2E TESTING (requires full environment setup)
# ============================================================

test-e2e: venv ## Run all e2e tests
	$(VENV) pytest backend/tests/e2e mcp_server/tests/e2e telegram_bot/tests/e2e -v $(PYTEST_ARGS)

test-backend-e2e: venv ## Run backend e2e tests only
	$(VENV) pytest backend/tests/e2e -v $(PYTEST_ARGS)

test-mcp-e2e: venv ## Run MCP server e2e tests only
	$(VENV) pytest mcp_server/tests/e2e -v $(PYTEST_ARGS)

test-telegram-e2e: venv ## Run Telegram bot e2e tests only
	$(VENV) pytest telegram_bot/tests/e2e -v $(PYTEST_ARGS)

# ============================================================
# DOCKER
# ============================================================

logs: ## View logs (use SERVICE=name, ENV=prod for production)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Viewing logs from all services..."; \
		$(COMPOSE_CMD) $(COMPOSE_FILES) logs -f; \
	else \
		echo "Viewing logs from $(SERVICE)..."; \
		$(COMPOSE_CMD) $(COMPOSE_FILES) logs -f $(SERVICE); \
	fi

rebuild: ## Rebuild Docker containers (use ENV=prod for production)
	@echo "Rebuilding containers..."
	@$(COMPOSE_CMD) $(COMPOSE_FILES) build --no-cache
	@echo "Containers rebuilt."

restart: stop start ## Restart all services

health: ## Check service health (use ENV=prod for production)
	@echo "Checking service health..."
	@$(COMPOSE_CMD) $(COMPOSE_FILES) ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

shell: ## Access service shell (use SERVICE=name, ENV=prod for production)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Error: SERVICE variable is required"; \
		echo "Usage: make shell SERVICE=backend"; \
		exit 1; \
	fi
	@echo "Accessing $(SERVICE) shell..."
	@$(COMPOSE_CMD) $(COMPOSE_FILES) exec $(SERVICE) /bin/bash || $(COMPOSE_CMD) $(COMPOSE_FILES) exec $(SERVICE) /bin/sh

check-loki: ## Verify Loki Docker plugin is installed (for production logging)
	@if docker plugin ls 2>/dev/null | grep -q "loki.*true"; then \
		echo "✓ Loki plugin installed and enabled"; \
	else \
		echo "✗ Loki plugin not installed or not enabled"; \
		echo "Install with: docker plugin install grafana/loki-docker-driver:latest --alias loki --grant-all-permissions"; \
		exit 1; \
	fi

# ============================================================
# GITHUB ENVIRONMENT MANAGEMENT
# ============================================================

gh: ## Interactive GitHub environment manager
	@python3 scripts/github_env.py

gh-read: ## Read GitHub environment variables/secrets
	@python3 scripts/github_env.py read --env $(ENV)

gh-diff: ## Show diff between local .env and GitHub
	@python3 scripts/github_env.py diff --env $(ENV)

gh-download: ## Download from GitHub to local .env (GitHub → local)
	@python3 scripts/github_env.py download --env $(ENV)

gh-upload: ## Upload local .env to GitHub (local → GitHub)
	@python3 scripts/github_env.py upload --env $(ENV)

gh-write: ## Write all .env values to GitHub (creates & overwrites)
	@python3 scripts/github_env.py write --env $(ENV)

# ============================================================
# HOST TERMINAL MCP
# ============================================================

terminal-start: ## Start host-terminal-mcp server
	@echo "Starting host-terminal-mcp..."
	@pkill -f "host-terminal-mcp --http" 2>/dev/null || true
	@sleep 1
	@if command -v uv >/dev/null 2>&1; then \
		uv tool install --force 'host-terminal-mcp[http]' >/dev/null 2>&1; \
		PORT=$${HOST_TERMINAL_PORT:-8099}; \
		MODE=$${HOST_TERMINAL_MODE:-allowlist}; \
		setsid nohup host-terminal-mcp --http --port $$PORT --mode $$MODE > /tmp/host-terminal-mcp.log 2>&1 & disown; \
		sleep 2; \
		if curl -s "http://localhost:$$PORT/health" >/dev/null 2>&1; then \
			echo "✓ host-terminal-mcp running on port $$PORT (mode: $$MODE)"; \
		else \
			echo "✗ Failed to start. Check /tmp/host-terminal-mcp.log"; \
		fi; \
	else \
		echo "Error: uv not installed. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"; \
	fi

terminal-stop: ## Stop host-terminal-mcp server
	@echo "Stopping host-terminal-mcp..."
	@pkill -f "host-terminal-mcp --http" 2>/dev/null && echo "✓ Stopped" || echo "Not running"

terminal-logs: ## View host-terminal-mcp logs
	@if [ -f /tmp/host-terminal-mcp.log ]; then \
		tail -f /tmp/host-terminal-mcp.log; \
	else \
		echo "No log file found at /tmp/host-terminal-mcp.log"; \
	fi
