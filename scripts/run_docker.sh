#!/bin/bash
# Annie Docker Startup Script
# Checks Docker installation, creates .env if missing, and starts services
# Supports environment modes: dev (default) and prod (with Grafana Loki logging)
#
# Usage:
#   ./run_docker.sh           # Development mode (default)
#   ENV=prod ./run_docker.sh  # Production mode with Loki logging

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Change to project root
cd "$PROJECT_ROOT"

echo -e "${GREEN}Annie Docker Startup Script${NC}"
echo "================================"
echo ""

# Function: Check if Docker is installed
check_docker() {
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}Error: Docker is not installed${NC}"
        echo "Please install Docker from: https://www.docker.com/get-started"
        exit 1
    fi
    
    # Check Docker version (require 20.10+)
    DOCKER_VERSION=$(docker --version | grep -oE '[0-9]+\.[0-9]+' | head -1)
    DOCKER_MAJOR=$(echo "$DOCKER_VERSION" | cut -d. -f1)
    DOCKER_MINOR=$(echo "$DOCKER_VERSION" | cut -d. -f2)
    
    if [ "$DOCKER_MAJOR" -lt 20 ] || ([ "$DOCKER_MAJOR" -eq 20 ] && [ "$DOCKER_MINOR" -lt 10 ]); then
        echo -e "${YELLOW}Warning: Docker version $DOCKER_VERSION detected. Docker 20.10+ recommended.${NC}"
    else
        echo -e "${GREEN}✓ Docker installed (version $DOCKER_VERSION)${NC}"
    fi
}

# Function: Check if Docker Compose is available
check_docker_compose() {
    # Check for docker compose (v2) or docker-compose (v1)
    if docker compose version &> /dev/null; then
        echo -e "${GREEN}✓ Docker Compose available (v2)${NC}"
        COMPOSE_CMD="docker compose"
    elif command -v docker-compose &> /dev/null; then
        echo -e "${GREEN}✓ Docker Compose available (v1)${NC}"
        COMPOSE_CMD="docker-compose"
    else
        echo -e "${RED}Error: Docker Compose is not available${NC}"
        echo "Please install Docker Compose"
        exit 1
    fi
}

# Function: Create .env file from env.example
create_env_file() {
    if [ ! -f ".env" ]; then
        echo -e "${YELLOW}.env file not found${NC}"
        echo ""
        read -p "Create .env file from env.example? (y/n): " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            cp env.example .env
            echo -e "${GREEN}✓ Created .env file from env.example${NC}"
            echo ""
            echo -e "${YELLOW}⚠ IMPORTANT: Please edit .env and fill in your actual API keys and tokens${NC}"
            echo "Required variables:"
            echo "  - TELEGRAM_BOT_TOKEN"
            echo "  - GROK_API_KEY or CHATGPT_API_KEY (based on LLM_PROVIDER)"
            echo "  - AGENTIC_MEMORIES_URL"
            echo "  - BRAVE_SEARCH_API_KEY (for internet access tool)"
            echo "  - STOCK_API_KEY (for stock trader tool)"
            echo ""
            read -p "Press Enter to continue after updating .env, or Ctrl+C to exit..."
        else
            echo -e "${RED}Error: .env file is required${NC}"
            exit 1
        fi
    else
        echo -e "${GREEN}✓ .env file exists${NC}"
    fi
}

# Function: Validate .env file has required variables
validate_env() {
    if [ ! -f ".env" ]; then
        echo -e "${RED}Error: .env file not found${NC}"
        exit 1
    fi
    
    # Source .env file
    set -a
    source .env
    set +a
    
    # Check for required variables
    MISSING_VARS=()
    
    if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ "$TELEGRAM_BOT_TOKEN" = "REPLACE_ME" ]; then
        MISSING_VARS+=("TELEGRAM_BOT_TOKEN")
    fi
    
    if [ -z "$AGENTIC_MEMORIES_URL" ] || [ "$AGENTIC_MEMORIES_URL" = "REPLACE_ME" ]; then
        MISSING_VARS+=("AGENTIC_MEMORIES_URL")
    fi
    
    # Check LLM provider keys
    if [ "$LLM_PROVIDER" = "grok-4" ]; then
        if [ -z "$GROK_API_KEY" ] || [ "$GROK_API_KEY" = "REPLACE_ME" ]; then
            MISSING_VARS+=("GROK_API_KEY")
        fi
    elif [ "$LLM_PROVIDER" = "chatgpt-5" ]; then
        if [ -z "$CHATGPT_API_KEY" ] || [ "$CHATGPT_API_KEY" = "REPLACE_ME" ]; then
            MISSING_VARS+=("CHATGPT_API_KEY")
        fi
    fi
    
    if [ ${#MISSING_VARS[@]} -gt 0 ]; then
        echo -e "${YELLOW}Warning: The following required variables are missing or not set in .env:${NC}"
        for var in "${MISSING_VARS[@]}"; do
            echo "  - $var"
        done
        echo ""
        echo "Services may fail to start without these variables."
        read -p "Continue anyway? (y/n): " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    else
        echo -e "${GREEN}✓ Required environment variables are set${NC}"
    fi

    # Set ENV from ENVIRONMENT variable in .env (for production logging detection)
    # Priority: ENV shell variable > ENVIRONMENT from .env > default "dev"
    if [ -z "$ENV" ]; then
        ENV="${ENVIRONMENT:-dev}"
    fi
    export ENV
}

# Function: Check if Loki Docker plugin is installed, install if missing (production only)
check_loki_plugin() {
    if docker plugin ls 2>/dev/null | grep -q "loki.*true"; then
        echo -e "${GREEN}✓ Loki Docker plugin installed and enabled${NC}"
        return 0
    fi

    # Check if plugin exists but is disabled
    if docker plugin ls 2>/dev/null | grep -q "loki.*false"; then
        echo -e "${YELLOW}Loki plugin found but disabled. Enabling...${NC}"
        if docker plugin enable loki 2>/dev/null; then
            echo -e "${GREEN}✓ Loki Docker plugin enabled${NC}"
            return 0
        else
            echo -e "${RED}Error: Failed to enable Loki plugin${NC}"
            exit 1
        fi
    fi

    # Plugin not installed - install it
    echo -e "${YELLOW}Loki Docker plugin not found. Installing...${NC}"
    echo ""
    if docker plugin install grafana/loki-docker-driver:latest --alias loki --grant-all-permissions; then
        echo ""
        echo -e "${GREEN}✓ Loki Docker plugin installed successfully${NC}"
        return 0
    else
        echo -e "${RED}Error: Failed to install Loki Docker plugin${NC}"
        echo ""
        echo "You can try manually:"
        echo "  docker plugin install grafana/loki-docker-driver:latest --alias loki --grant-all-permissions"
        echo ""
        echo "Or run in dev mode: ENV=dev make start"
        exit 1
    fi
}

# Function: Validate production-specific environment variables
validate_prod_env() {
    if [ -z "$LOKI_URL" ] || [ "$LOKI_URL" = "REPLACE_ME" ]; then
        echo -e "${RED}Error: LOKI_URL required for production mode${NC}"
        echo ""
        echo "Set in .env:"
        echo "  LOKI_URL=https://<user-id>:<api-key>@logs-prod-us-central1.grafana.net/loki/api/v1/push"
        echo ""
        echo "Get your URL from: Grafana Cloud -> Connections -> Hosted Logs -> Loki -> Details"
        echo ""
        echo "Or run in dev mode: ENV=dev make start"
        exit 1
    fi
    echo -e "${GREEN}✓ LOKI_URL configured${NC}"
}

# Function: Manage host-terminal-mcp server (for execute_command tool)
manage_host_terminal_mcp() {
    echo ""
    echo -e "${GREEN}Managing host-terminal-mcp server...${NC}"
    
    # Configuration
    HOST_TERMINAL_PORT="${HOST_TERMINAL_PORT:-8099}"
    HOST_TERMINAL_MODE="${HOST_TERMINAL_MODE:-allowlist}"
    HOST_TERMINAL_LOG="/tmp/host-terminal-mcp.log"
    
    # Stop any existing host-terminal-mcp processes
    if pgrep -f "host-terminal-mcp" > /dev/null 2>&1; then
        echo -e "${YELLOW}Stopping existing host-terminal-mcp server...${NC}"
        pkill -f "host-terminal-mcp" 2>/dev/null || true
        sleep 1
        # Force kill if still running
        if pgrep -f "host-terminal-mcp" > /dev/null 2>&1; then
            pkill -9 -f "host-terminal-mcp" 2>/dev/null || true
            sleep 1
        fi
        echo -e "${GREEN}✓ Stopped existing server${NC}"
    fi
    
    # Check if uv is available
    if ! command -v uv &> /dev/null; then
        echo -e "${YELLOW}Warning: uv not installed, skipping host-terminal-mcp${NC}"
        echo "Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
        echo "Then restart Annie to enable terminal access"
        return 0
    fi
    
    # Install/update host-terminal-mcp with HTTP extras
    echo "Installing/updating host-terminal-mcp..."
    if uv tool install --force 'host-terminal-mcp[http]' > /dev/null 2>&1; then
        echo -e "${GREEN}✓ host-terminal-mcp installed/updated${NC}"
    else
        echo -e "${YELLOW}Warning: Failed to install host-terminal-mcp${NC}"
        echo "Terminal command execution will be unavailable"
        return 0
    fi
    
    # Start server in background (setsid + disown to fully detach from parent shell/session)
    echo "Starting host-terminal-mcp on port $HOST_TERMINAL_PORT (mode: $HOST_TERMINAL_MODE)..."
    setsid nohup host-terminal-mcp --http --port "$HOST_TERMINAL_PORT" --mode "$HOST_TERMINAL_MODE" > "$HOST_TERMINAL_LOG" 2>&1 &
    disown
    
    # Wait for server to start
    sleep 2
    
    # Verify server is running
    if curl -s "http://localhost:$HOST_TERMINAL_PORT/health" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ host-terminal-mcp running on port $HOST_TERMINAL_PORT${NC}"
        echo "  Log file: $HOST_TERMINAL_LOG"
    else
        echo -e "${YELLOW}Warning: host-terminal-mcp may not have started correctly${NC}"
        echo "  Check log: $HOST_TERMINAL_LOG"
        echo "  Terminal command execution may be unavailable"
    fi
}

# Function: Start Docker services
start_services() {
    echo ""

    if [ "$ENV" = "prod" ]; then
        echo -e "${GREEN}Starting Annie services (${YELLOW}production${GREEN} mode)...${NC}"
        echo ""
        # Production mode: use base + prod override for Loki logging
        $COMPOSE_CMD -f docker-compose.yml -f docker-compose.prod.yml up --build -d "$@"
        echo ""
        echo -e "${GREEN}✓ Services started with Loki logging enabled${NC}"
        echo ""
        echo "View logs at: https://grafana.com (your Grafana Cloud dashboard)"
    else
        echo -e "${GREEN}Starting Annie services (${YELLOW}development${GREEN} mode)...${NC}"
        echo ""
        # Development mode: use base compose only
        $COMPOSE_CMD up --build -d "$@"
        echo ""
        echo -e "${GREEN}✓ Services started in development mode${NC}"
    fi

    echo ""
    echo "Use 'make logs' to view logs"
    echo "Use 'make stop' to stop services"
    echo "Use 'make health' to check service status"
}

# Main execution
main() {
    check_docker
    check_docker_compose
    create_env_file
    validate_env

    # Production-specific checks
    if [ "$ENV" = "prod" ]; then
        echo ""
        echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${YELLOW}Production mode enabled (ENV=prod)${NC}"
        echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        check_loki_plugin
        validate_prod_env
    fi

    # Start host-terminal-mcp server (runs on host, not in Docker)
    manage_host_terminal_mcp

    # Start services with any additional arguments passed to script
    start_services "$@"
}

# Run main function
main "$@"
