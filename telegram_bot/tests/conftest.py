"""
Pytest configuration and shared fixtures for Telegram bot tests.

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
from unittest.mock import MagicMock, AsyncMock

# Test environment variables - SET BEFORE ANY PROJECT IMPORTS
TEST_ENV_VARS = {
    # Environment
    "ENVIRONMENT": "test",
    "LOG_LEVEL": "DEBUG",
    # Telegram Configuration
    "TELEGRAM_BOT_TOKEN": "test-telegram-token-12345",
    "AUTHORIZED_USER_IDS": "12345,67890",
    "POLLING_TIMEOUT": "30",
    "MAX_RETRIES": "3",
    # Backend Configuration
    "BACKEND_URL": "http://localhost:8000",
    "BACKEND_CONNECT_TIMEOUT": "5",
    "BACKEND_SOCK_READ_TIMEOUT": "30",
    # Timeouts
    "TELEGRAM_FIRST_TOKEN_TIMEOUT": "30",
}

# Set environment variables at module load time
for key, value in TEST_ENV_VARS.items():
    os.environ.setdefault(key, value)

# Now safe to import pytest
import pytest  # noqa: E402

# Add telegram_bot directory to Python path for imports
telegram_bot_dir = Path(__file__).parent.parent
sys.path.insert(0, str(telegram_bot_dir))


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Ensure test environment variables are set for each test."""
    for key, value in TEST_ENV_VARS.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def mock_telegram_update():
    """Mock Telegram update object."""
    update = MagicMock()
    update.effective_user.id = 12345
    update.effective_user.username = "testuser"
    update.effective_user.first_name = "Test"
    update.message.text = "Hello, Annie!"
    update.message.chat_id = 12345
    update.message.message_id = 1
    return update


@pytest.fixture
def mock_telegram_context():
    """Mock Telegram context object."""
    context = MagicMock()
    context.bot = AsyncMock()
    context.bot.send_message = AsyncMock()
    context.bot.edit_message_text = AsyncMock()
    return context


@pytest.fixture
def mock_httpx_client():
    """Mock httpx client for backend API calls."""
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None
    return client


class MockRedisPipeline:
    """Mock Redis pipeline for atomic operations."""

    def __init__(self, client):
        self._client = client
        self._operations = []

    def get(self, key: str):
        """Queue a GET operation."""
        self._operations.append(('get', key))
        return self

    def delete(self, key: str):
        """Queue a DELETE operation."""
        self._operations.append(('delete', key))
        return self

    async def execute(self):
        """Execute all queued operations and return results."""
        results = []
        for op, key in self._operations:
            if op == 'get':
                results.append(self._client._data.get(key))
            elif op == 'delete':
                deleted = 1 if key in self._client._data else 0
                self._client._data.pop(key, None)
                self._client._ttls.pop(key, None)
                results.append(deleted)
        return results

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class MockRedisClient:
    """In-memory mock of async Redis client for testing."""

    def __init__(self):
        self._data = {}
        self._ttls = {}

    async def get(self, key: str):
        """Get value for key."""
        return self._data.get(key)

    async def set(self, key: str, value: str, ex: int = None, nx: bool = False):
        """Set key to value with optional expiry and NX flag."""
        if nx and key in self._data:
            return None
        self._data[key] = value
        if ex:
            self._ttls[key] = ex
        return True

    async def delete(self, *keys):
        """Delete one or more keys."""
        deleted = 0
        for key in keys:
            if key in self._data:
                del self._data[key]
                self._ttls.pop(key, None)
                deleted += 1
        return deleted

    async def ttl(self, key: str):
        """Get TTL for key."""
        return self._ttls.get(key, -2)

    def pipeline(self):
        """Create a pipeline for atomic operations."""
        return MockRedisPipeline(self)

    async def flushdb(self):
        """Clear all data."""
        self._data.clear()
        self._ttls.clear()

    async def close(self):
        """Close connection (no-op for mock)."""
        pass


@pytest.fixture
def mock_redis_client():
    """Create an in-memory mock Redis client for testing."""
    return MockRedisClient()
