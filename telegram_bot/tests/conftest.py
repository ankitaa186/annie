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
import pytest

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
