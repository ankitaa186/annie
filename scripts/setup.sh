#!/bin/bash
# Annie First-Boot Setup Script
# Thin bash wrapper that checks bare-minimum prerequisites,
# then bootstraps the Python setup wizard for an interactive experience.
#
# Usage:
#   ./scripts/setup.sh        # Interactive first-boot setup
#   make setup                 # Same, via Makefile

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo ""
echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${CYAN}${BOLD}║       Annie — First-Boot Setup           ║${NC}"
echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""

# ─── Phase 0: Detect bare-minimum prerequisites ───────────────────────

ERRORS=()
WARNINGS=()

# Check Python 3.10+ (minimum for the wizard; Annie services need 3.12+ but Docker handles that)
PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PY_VERSION=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
        PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
        if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 10 ]; then
            PYTHON_CMD="$cmd"
            echo -e "${GREEN}✓ Python $PY_VERSION found ($cmd)${NC}"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    ERRORS+=("Python 3.10+ is required but not found. Install from https://www.python.org/downloads/")
fi

# Check Docker (not required yet — wizard will handle gracefully)
if command -v docker &>/dev/null; then
    DOCKER_VERSION=$(docker --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+' | head -1)
    if [ -n "$DOCKER_VERSION" ]; then
        echo -e "${GREEN}✓ Docker $DOCKER_VERSION found${NC}"
    else
        echo -e "${GREEN}✓ Docker found${NC}"
    fi

    # Check if Docker daemon is actually running
    if ! docker info &>/dev/null 2>&1; then
        WARNINGS+=("Docker is installed but the daemon is not running. Start Docker Desktop or the Docker service before proceeding.")
    fi
else
    WARNINGS+=("Docker is not installed. You'll need it to run Annie's services. Install from https://docs.docker.com/get-docker/")
fi

# Check Docker Compose
if docker compose version &>/dev/null 2>&1; then
    echo -e "${GREEN}✓ Docker Compose v2 found${NC}"
elif command -v docker-compose &>/dev/null; then
    echo -e "${GREEN}✓ Docker Compose v1 found${NC}"
elif command -v docker &>/dev/null; then
    WARNINGS+=("Docker Compose not found. It's required to run Annie. Install Docker Desktop (includes Compose) or install it separately.")
fi

# Check git
if command -v git &>/dev/null; then
    echo -e "${GREEN}✓ Git found${NC}"
else
    WARNINGS+=("Git is not installed. You'll need it if you want to auto-deploy agentic-memories.")
fi

# Print errors / warnings
if [ ${#WARNINGS[@]} -gt 0 ]; then
    echo ""
    for warn in "${WARNINGS[@]}"; do
        echo -e "  ${YELLOW}⚠ $warn${NC}"
    done
fi

if [ ${#ERRORS[@]} -gt 0 ]; then
    echo ""
    for err in "${ERRORS[@]}"; do
        echo -e "  ${RED}✗ $err${NC}"
    done
    echo ""
    echo -e "${RED}Cannot continue without the prerequisites above.${NC}"
    exit 1
fi

echo ""

# ─── Phase 1: Bootstrap Python wizard dependencies ────────────────────

WIZARD="$SCRIPT_DIR/setup_wizard.py"
if [ ! -f "$WIZARD" ]; then
    echo -e "${RED}Error: setup_wizard.py not found at $WIZARD${NC}"
    exit 1
fi

# Use a lightweight venv in .setup_venv (separate from dev .venv)
SETUP_VENV="$PROJECT_ROOT/.setup_venv"

install_wizard_deps() {
    echo -e "${CYAN}Installing setup wizard dependencies...${NC}"

    if command -v uv &>/dev/null; then
        # Fast path with uv
        if [ ! -d "$SETUP_VENV" ]; then
            uv venv --python "$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" "$SETUP_VENV" >/dev/null 2>&1 || \
            uv venv "$SETUP_VENV" >/dev/null 2>&1
        fi
        SETUP_PIP="uv pip install --python $SETUP_VENV/bin/python -q"
    else
        # Fallback to regular venv + pip
        if [ ! -d "$SETUP_VENV" ]; then
            "$PYTHON_CMD" -m venv "$SETUP_VENV"
        fi
        SETUP_PIP="$SETUP_VENV/bin/pip install -q"
    fi

    $SETUP_PIP questionary httpx 2>/dev/null
    echo -e "${GREEN}✓ Dependencies ready${NC}"
    echo ""
}

# Check if deps are already available in the setup venv
if [ -d "$SETUP_VENV" ] && "$SETUP_VENV/bin/python" -c "import questionary, httpx" 2>/dev/null; then
    : # Already good
else
    install_wizard_deps
fi

# ─── Phase 2: Launch Python wizard ────────────────────────────────────

exec "$SETUP_VENV/bin/python" "$WIZARD" "$@"
