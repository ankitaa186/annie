"""
Pytest configuration and shared fixtures for backend tests.

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

# Detect if running inside Docker container
def _is_running_in_docker():
    """Check if we're running inside a Docker container."""
    return os.path.exists("/.dockerenv") or os.environ.get("DOCKER_CONTAINER") == "true"

# Use Docker service names when running inside container, localhost otherwise
_REDIS_HOST = "redis" if _is_running_in_docker() else "localhost"
_AGENTIC_MEMORIES_HOST = "host.docker.internal" if _is_running_in_docker() else "localhost"

# Test environment variables - SET BEFORE ANY PROJECT IMPORTS
TEST_ENV_VARS = {
    # Environment
    "ENVIRONMENT": "test",
    "LOG_LEVEL": "DEBUG",
    # LLM Configuration
    "LLM_MODEL": "grok-4-fast",
    "LLM_PROVIDER": "grok-4-fast",
    "GROK_API_KEY": "test-grok-key-12345",
    "CHATGPT_API_KEY": "test-chatgpt-key-12345",
    "GEMINI_API_KEY": "test-gemini-key-12345",
    "GEMINI_MODEL": "gemini-3.1-pro-preview",
    "GEMINI_MAX_OUTPUT_TOKENS": "8192",
    "GEMINI_TEMPERATURE": "1.0",
    "GEMINI_SAFETY_SETTING": "BLOCK_NONE",
    "GEMINI_CONTEXT_CACHE_TTL": "300",
    "GROK_LIVE_SEARCH_MODE": "auto",
    "GROK_LIVE_SEARCH_MAX_RESULTS": "10",
    "GROK_LIVE_SEARCH_COST_ALERT_THRESHOLD": "100",
    # Telegram (not used in backend tests but may be needed for imports)
    "TELEGRAM_BOT_TOKEN": "test-telegram-token",
    "AUTHORIZED_USER_IDS": "12345,67890",
    "POLLING_TIMEOUT": "30",
    "MAX_RETRIES": "3",
    # Tool API Keys
    "BRAVE_SEARCH_API_KEY": "test-brave-key",
    "STOCK_API_KEY": "test-stock-key",
    # External Services
    "AGENTIC_MEMORIES_URL": f"http://{_AGENTIC_MEMORIES_HOST}:8080",
    # Langfuse (disabled for tests)
    "LANGFUSE_PUBLIC_KEY": "",
    "LANGFUSE_SECRET_KEY": "",
    "LANGFUSE_HOST": "https://us.cloud.langfuse.com",
    "LANGFUSE_PROJECT_NAME": "annie-test",
    "LANGFUSE_ENVIRONMENT": "test",
    # Redis - use Docker service name when in container
    "REDIS_HOST": _REDIS_HOST,
    "REDIS_PORT": "6379",
    # Service Configuration
    "BACKEND_PORT": "8001",
    "BACKEND_URL": "http://localhost:8000",
    "MCP_SERVER_PORT": "8002",
    "MCP_SERVER_URL": "http://localhost:8002",
    # Timeouts
    "LLM_REQUEST_TIMEOUT": "30",
    "LLM_FAILOVER_TIMEOUT": "30",
    "LLM_STREAMING_TIMEOUT": "30",
    "BACKEND_CONNECT_TIMEOUT": "5",
    "BACKEND_SOCK_READ_TIMEOUT": "30",
    "TELEGRAM_FIRST_TOKEN_TIMEOUT": "30",
}

# Set environment variables at module load time
for key, value in TEST_ENV_VARS.items():
    os.environ.setdefault(key, value)

# Now safe to import pytest
import pytest

# Add backend directory to Python path for imports
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Ensure test environment variables are set for each test."""
    for key, value in TEST_ENV_VARS.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def mock_redis():
    """Mock Redis client for tests."""
    redis_mock = MagicMock()
    redis_mock.ping.return_value = True
    redis_mock.get.return_value = None
    redis_mock.set.return_value = True
    redis_mock.setex.return_value = True
    redis_mock.delete.return_value = 1
    redis_mock.lpush.return_value = 1
    redis_mock.rpop.return_value = None
    redis_mock.lrange.return_value = []
    redis_mock.llen.return_value = 0
    return redis_mock


@pytest.fixture
def mock_httpx_client():
    """Mock httpx client for HTTP requests."""
    from unittest.mock import AsyncMock

    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None
    return client
