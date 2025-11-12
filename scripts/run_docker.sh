#!/bin/bash
# Annie Docker Startup Script
# Checks Docker installation, creates .env if missing, and starts services

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
}

# Function: Start Docker services
start_services() {
    echo ""
    echo -e "${GREEN}Starting Annie services...${NC}"
    echo ""

    # Run docker-compose up in detached mode
    $COMPOSE_CMD up --build -d "$@"

    echo ""
    echo -e "${GREEN}✓ Services started in detached mode${NC}"
    echo ""
    echo "Use 'docker compose logs -f' to view logs"
    echo "Use 'docker compose ps' to check service status"
    echo "Use 'docker compose down' to stop services"
}

# Main execution
main() {
    check_docker
    check_docker_compose
    create_env_file
    validate_env
    
    # Start services with any additional arguments passed to script
    start_services "$@"
}

# Run main function
main "$@"
