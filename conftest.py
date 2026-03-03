"""
Root-level pytest configuration.

This conftest sets environment variables BEFORE any test collection happens,
ensuring all modules can import correctly during collection phase.
"""

import os

# Set all test environment variables before any imports
# This runs when pytest loads conftest, before collecting tests

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
    # Telegram
    "TELEGRAM_BOT_TOKEN": "test-telegram-token-12345",
    "AUTHORIZED_USER_IDS": "12345,67890",
    "POLLING_TIMEOUT": "30",
    "MAX_RETRIES": "3",
    # Tool API Keys
    "BRAVE_SEARCH_API_KEY": "test-brave-key",
    "STOCK_API_KEY": "test-stock-key",
    # External Services
    "AGENTIC_MEMORIES_URL": "http://localhost:8080",
    # Langfuse (disabled for tests)
    "LANGFUSE_PUBLIC_KEY": "",
    "LANGFUSE_SECRET_KEY": "",
    "LANGFUSE_HOST": "https://us.cloud.langfuse.com",
    "LANGFUSE_PROJECT_NAME": "annie-test",
    "LANGFUSE_ENVIRONMENT": "test",
    # Redis
    "REDIS_HOST": "localhost",
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

# Set environment variables at module load time (before test collection)
for key, value in TEST_ENV_VARS.items():
    os.environ.setdefault(key, value)
