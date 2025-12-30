"""
Pytest configuration and shared fixtures for MCP server tests.

Provides:
- Environment variable mocking for tests
- Common test fixtures
- Path setup for imports

IMPORTANT: Environment variables are set at module level (before any imports)
to ensure they're available during module initialization.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Test environment variables - SET BEFORE ANY PROJECT IMPORTS
TEST_ENV_VARS = {
    # Environment
    "ENVIRONMENT": "test",
    "LOG_LEVEL": "DEBUG",
    # External Services
    "AGENTIC_MEMORIES_URL": "http://localhost:8080",
    # Tool API Keys
    "BRAVE_SEARCH_API_KEY": "test-brave-key",
    "STOCK_API_KEY": "test-stock-key",
    # Reddit API (optional - tests mock when needed)
    "REDDIT_USER_AGENT": "annie-bot/1.0 test",
    # MCP Server Configuration
    "MCP_SERVER_PORT": "8002",
}

# Set environment variables at module load time
for key, value in TEST_ENV_VARS.items():
    os.environ.setdefault(key, value)

# Now safe to import pytest
import pytest

# Add mcp_server directory to Python path for imports
mcp_server_dir = Path(__file__).parent.parent
sys.path.insert(0, str(mcp_server_dir))


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Ensure test environment variables are set for each test."""
    for key, value in TEST_ENV_VARS.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def mock_httpx_client():
    """Mock httpx client for HTTP requests."""
    from unittest.mock import AsyncMock

    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None
    return client


@pytest.fixture
def mock_agentic_memories_response():
    """Mock successful agentic-memories response."""
    return {
        "status": "success",
        "memory_id": "mem_test123",
        "stored_at": "2025-01-01T00:00:00Z",
    }
