# Annie Makefile
# Development commands for managing Annie services

.PHONY: help install venv test test-unit test-integration test-backend test-mcp test-telegram coverage start stop logs clean clean-venv clean-all rebuild restart health shell lint format format-check gh gh-read gh-diff gh-write gh-update

# Detect Docker Compose command (v2 or v1)
COMPOSE_CMD := $(shell if docker compose version >/dev/null 2>&1; then echo "docker compose"; else echo "docker-compose"; fi)

# Activate venv for all test commands
VENV := . .venv/bin/activate &&

# Default target
help: ## Show this help message
	@echo "Annie Development Commands"
	@echo "=========================="
	@echo ""
	@echo "  Setup:"
	@grep -E '^(install|start|stop|clean|clean-venv|clean-all):.*## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "    \033[36m%-18s\033[0m %s\n", $$1, $$2}'
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
	@echo "  GitHub (use ENV=prod for production):"
	@grep -E '^gh[a-zA-Z0-9_-]*:.*## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "    \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ============================================================
# SETUP
# ============================================================

# Ensure venv exists and dependencies are installed
.venv/bin/activate: backend/requirements.txt mcp_server/requirements.txt telegram_bot/requirements.txt
	@if [ ! -d ".venv" ]; then \
		echo "Creating virtual environment..."; \
		python3 -m venv .venv; \
	fi
	@echo "Installing dependencies..."
	@$(VENV) pip install -q -r backend/requirements.txt
	@$(VENV) pip install -q -r mcp_server/requirements.txt
	@$(VENV) pip install -q -r telegram_bot/requirements.txt
	@touch .venv/bin/activate

venv: .venv/bin/activate ## Setup venv and install all dependencies

install: venv ## Setup venv and install dependencies
	@echo "Dependencies installed in .venv/"

start: ## Start all Docker services
	@echo "Starting Annie services..."
	@./scripts/run_docker.sh

stop: ## Stop all Docker services
	@echo "Stopping Annie services..."
	@$(COMPOSE_CMD) down
	@echo "Services stopped."

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

lint: venv ## Run linters (ruff)
	$(VENV) pip install -q ruff
	$(VENV) ruff check backend/ mcp_server/ telegram_bot/

format: venv ## Format code (ruff)
	$(VENV) pip install -q ruff
	$(VENV) ruff format backend/ mcp_server/ telegram_bot/

format-check: venv ## Check code formatting without changes
	$(VENV) pip install -q ruff
	$(VENV) ruff format --check backend/ mcp_server/ telegram_bot/

# ============================================================
# TESTING - All Services
# ============================================================

test: venv ## Run all tests (unit + integration)
	$(VENV) pytest backend/tests mcp_server/tests telegram_bot/tests -v $(PYTEST_ARGS)

test-unit: venv ## Run unit tests only
	$(VENV) pytest backend/tests/unit mcp_server/tests telegram_bot/tests/unit -v $(PYTEST_ARGS)

test-integration: venv ## Run integration tests only
	$(VENV) pytest backend/tests/integration telegram_bot/tests/integration -v $(PYTEST_ARGS)

coverage: venv ## Run tests with coverage report
	$(VENV) pip install -q pytest-cov
	$(VENV) pytest backend/tests mcp_server/tests telegram_bot/tests --cov=backend/api --cov=mcp_server --cov=telegram_bot --cov-report=term-missing --cov-report=html $(PYTEST_ARGS)
	@echo "HTML coverage report: htmlcov/index.html"

# ============================================================
# TESTING - Individual Services
# ============================================================

test-backend: venv ## Run backend tests only
	$(VENV) pytest backend/tests -v $(PYTEST_ARGS)

test-mcp: venv ## Run MCP server tests only
	$(VENV) pytest mcp_server/tests -v $(PYTEST_ARGS)

test-telegram: venv ## Run Telegram bot tests only
	$(VENV) pytest telegram_bot/tests -v $(PYTEST_ARGS)

# ============================================================
# DOCKER
# ============================================================

logs: ## View logs (use SERVICE=name for specific service)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Viewing logs from all services..."; \
		$(COMPOSE_CMD) logs -f; \
	else \
		echo "Viewing logs from $(SERVICE)..."; \
		$(COMPOSE_CMD) logs -f $(SERVICE); \
	fi

rebuild: ## Rebuild Docker containers
	@echo "Rebuilding containers..."
	@$(COMPOSE_CMD) build --no-cache
	@echo "Containers rebuilt."

restart: stop start ## Restart all services

health: ## Check service health
	@echo "Checking service health..."
	@$(COMPOSE_CMD) ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

shell: ## Access service shell (use SERVICE=name)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Error: SERVICE variable is required"; \
		echo "Usage: make shell SERVICE=backend"; \
		exit 1; \
	fi
	@echo "Accessing $(SERVICE) shell..."
	@$(COMPOSE_CMD) exec $(SERVICE) /bin/bash || $(COMPOSE_CMD) exec $(SERVICE) /bin/sh

# ============================================================
# GITHUB ENVIRONMENT MANAGEMENT
# ============================================================

# Default environment is dev
ENV ?= dev

gh: ## Interactive GitHub environment manager
	@python3 scripts/github_env.py

gh-read: ## Read GitHub environment variables/secrets
	@python3 scripts/github_env.py read --env $(ENV)

gh-diff: ## Show diff between local .env and GitHub
	@python3 scripts/github_env.py diff --env $(ENV)

gh-write: ## Write all .env values to GitHub (creates & overwrites)
	@python3 scripts/github_env.py write --env $(ENV)

gh-update: ## Update only changed values in GitHub
	@python3 scripts/github_env.py update --env $(ENV)
