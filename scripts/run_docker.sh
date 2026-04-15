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
            echo "  - XAI_API_KEY, OPENAI_API_KEY, or GOOGLE_API_KEY (based on LLM_MODEL)"
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

# Helper: check if a variable is set and not a placeholder
is_set() {
    local val="${!1}"
    [ -n "$val" ] && [ "$val" != "REPLACE_ME" ]
}

# Function: Validate .env file has required variables
validate_env() {
    if [ ! -f ".env" ]; then
        echo -e "${RED}Error: .env file not found${NC}"
        echo "Run: cp env.example .env"
        exit 1
    fi

    # Source .env file
    set -a
    source .env
    set +a

    ERRORS=()
    WARNINGS=()

    # --- Required: Telegram ---
    if ! is_set TELEGRAM_BOT_TOKEN; then
        ERRORS+=("TELEGRAM_BOT_TOKEN - required for Telegram bot")
    fi
    if ! is_set AUTHORIZED_USER_IDS; then
        ERRORS+=("AUTHORIZED_USER_IDS - required to authorize Telegram users")
    fi

    # --- Required: External services ---
    if ! is_set AGENTIC_MEMORIES_URL; then
        ERRORS+=("AGENTIC_MEMORIES_URL - required for memory service")
    fi

    # --- Required: LLM API key for configured model ---
    # Resolve which model is configured
    LLM_MODEL_VAL="${LLM_MODEL:-grok-4-fast}"

    # Map model → required API key env var
    case "$LLM_MODEL_VAL" in
        grok-4-fast|grok-4)
            REQUIRED_KEY="XAI_API_KEY"
            REQUIRED_KEY_LABEL="XAI_API_KEY (required for model: $LLM_MODEL_VAL)"
            ;;
        gpt-5.4|chatgpt-5)
            REQUIRED_KEY="OPENAI_API_KEY"
            REQUIRED_KEY_LABEL="OPENAI_API_KEY (required for model: $LLM_MODEL_VAL)"
            ;;
        gemini-3.1-pro-preview|gemini-3-flash-preview|gemini-2.5-pro)
            REQUIRED_KEY="GOOGLE_API_KEY"
            REQUIRED_KEY_LABEL="GOOGLE_API_KEY (required for model: $LLM_MODEL_VAL)"
            ;;
        *)
            REQUIRED_KEY=""
            WARNINGS+=("LLM_MODEL='$LLM_MODEL_VAL' is not a recognized model")
            ;;
    esac

    if [ -n "$REQUIRED_KEY" ] && ! is_set "$REQUIRED_KEY"; then
        ERRORS+=("$REQUIRED_KEY_LABEL")
    fi

    # Also check that at least one LLM key exists (for fallback support)
    if ! is_set XAI_API_KEY && ! is_set OPENAI_API_KEY && ! is_set GOOGLE_API_KEY; then
        ERRORS+=("No LLM API keys set at all - need at least one of: XAI_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY")
    fi

    # --- Optional but recommended: warn if missing ---
    if ! is_set LANGFUSE_PUBLIC_KEY || ! is_set LANGFUSE_SECRET_KEY; then
        WARNINGS+=("LANGFUSE keys not set - LLM observability/tracing will be disabled")
    fi

    # --- Print results ---
    if [ ${#ERRORS[@]} -gt 0 ]; then
        echo ""
        echo -e "${RED}✗ Missing required environment variables:${NC}"
        for err in "${ERRORS[@]}"; do
            echo -e "  ${RED}✗${NC} $err"
        done
    fi

    if [ ${#WARNINGS[@]} -gt 0 ]; then
        echo ""
        echo -e "${YELLOW}⚠ Warnings:${NC}"
        for warn in "${WARNINGS[@]}"; do
            echo -e "  ${YELLOW}⚠${NC} $warn"
        done
    fi

    if [ ${#ERRORS[@]} -gt 0 ]; then
        echo ""
        echo -e "${RED}Fix the errors above in .env and try again.${NC}"
        exit 1
    fi

    if [ ${#ERRORS[@]} -eq 0 ] && [ ${#WARNINGS[@]} -eq 0 ]; then
        echo -e "${GREEN}✓ All required environment variables are set${NC}"
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

# Function: Clear stale session state from Redis
# Removes pending message locks and active request flags that survive restarts
clear_stale_redis_state() {
    echo ""
    echo "Clearing stale session state from Redis..."

    # Wait for Redis to be healthy
    local retries=10
    while [ $retries -gt 0 ]; do
        if $COMPOSE_CMD exec -T redis redis-cli PING 2>/dev/null | grep -q PONG; then
            break
        fi
        retries=$((retries - 1))
        sleep 1
    done

    if [ $retries -eq 0 ]; then
        echo -e "${YELLOW}Warning: Redis not ready, skipping stale state cleanup${NC}"
        return 0
    fi

    # Delete stale keys that block message processing after crashes.
    # processing:* is a 180s TTL flag the telegram-bot sets while handling a
    # message; if Redis drops mid-completion the clear call can fail and the
    # flag gets stuck, causing the user's next message to be queued as
    # "pending" even though nothing is actually processing. Safe to wipe
    # unconditionally here because the bot hasn't started yet.
    local cleared=0
    for pattern in "pending_message:*" "active_request:*" "processing:*"; do
        local keys
        keys=$($COMPOSE_CMD exec -T redis redis-cli KEYS "$pattern" 2>/dev/null | tr -d '\r')
        if [ -n "$keys" ]; then
            for key in $keys; do
                $COMPOSE_CMD exec -T redis redis-cli DEL "$key" > /dev/null 2>&1
                cleared=$((cleared + 1))
            done
        fi
    done

    if [ $cleared -gt 0 ]; then
        echo -e "${GREEN}✓ Cleared $cleared stale session key(s)${NC}"
    else
        echo -e "${GREEN}✓ No stale session state found${NC}"
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

    # Clear stale locks/pending states from previous crashes
    clear_stale_redis_state

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
