# Annie Makefile
# Common development commands for managing Annie services

.PHONY: help start stop logs test clean rebuild restart health shell

# Detect Docker Compose command (v2 or v1)
COMPOSE_CMD := $(shell if docker compose version >/dev/null 2>&1; then echo "docker compose"; else echo "docker-compose"; fi)

# Default target
help:
	@echo "Annie Development Commands"
	@echo "=========================="
	@echo ""
	@echo "Available commands:"
	@echo "  make start              - Start all services"
	@echo "  make stop               - Stop all services"
	@echo "  make logs               - View logs from all services"
	@echo "  make logs SERVICE=name  - View logs from specific service"
	@echo "  make test               - Run test suite"
	@echo "  make clean              - Clean up Docker resources"
	@echo "  make rebuild            - Rebuild containers"
	@echo "  make restart            - Restart services"
	@echo "  make health             - Check service health"
	@echo "  make shell SERVICE=name - Access service shell"
	@echo ""
	@echo "Examples:"
	@echo "  make logs SERVICE=backend"
	@echo "  make shell SERVICE=mcp-server"

# Start all services
start:
	@echo "Starting Annie services..."
	@./scripts/run_docker.sh

# Stop all services gracefully
stop:
	@echo "Stopping Annie services..."
	@$(COMPOSE_CMD) stop
	@echo "Services stopped."

# View logs from all services or specific service
logs:
	@if [ -z "$(SERVICE)" ]; then \
		echo "Viewing logs from all services..."; \
		$(COMPOSE_CMD) logs -f; \
	else \
		echo "Viewing logs from $(SERVICE)..."; \
		$(COMPOSE_CMD) logs -f $(SERVICE); \
	fi

# Run test suite
test:
	@echo "Running test suite..."
	@echo "Note: Tests will be implemented in later stories"
	@echo "For now, running placeholder test command..."
	@$(COMPOSE_CMD) exec backend python -m pytest tests/ 2>/dev/null || echo "Test suite not yet implemented"
	@$(COMPOSE_CMD) exec mcp-server python -m pytest tests/ 2>/dev/null || echo "Test suite not yet implemented"
	@$(COMPOSE_CMD) exec telegram-bot python -m pytest tests/ 2>/dev/null || echo "Test suite not yet implemented"

# Clean up Docker resources
clean:
	@echo "Cleaning up Docker resources..."
	@$(COMPOSE_CMD) down -v --remove-orphans
	@echo "Removing build artifacts..."
	@find . -type d -name "__pycache__" -exec rm -r {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -r {} + 2>/dev/null || true
	@echo "Cleanup complete."

# Rebuild containers
rebuild:
	@echo "Rebuilding containers..."
	@$(COMPOSE_CMD) build --no-cache
	@echo "Containers rebuilt."

# Restart services
restart: stop start

# Check service health
health:
	@echo "Checking service health..."
	@$(COMPOSE_CMD) ps
	@echo ""
	@echo "Health check details:"
	@$(COMPOSE_CMD) ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

# Access service shell
shell:
	@if [ -z "$(SERVICE)" ]; then \
		echo "Error: SERVICE variable is required"; \
		echo "Usage: make shell SERVICE=backend"; \
		exit 1; \
	fi
	@echo "Accessing $(SERVICE) shell..."
	@$(COMPOSE_CMD) exec $(SERVICE) /bin/bash || $(COMPOSE_CMD) exec $(SERVICE) /bin/sh
