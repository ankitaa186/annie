"""
Shared pytest fixtures for proactive AI integration tests.

Provides fixtures for:
- Mock IntentsClient
- Mock Redis client
- Mock Telegram bot
- Mock MCP client
- Sample intents (scheduled and condition)
- Sample user profiles
- Time mocking utilities
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, Mock
from typing import Dict, Any


# ============================================================================
# Mock IntentsClient
# ============================================================================

@pytest.fixture
def mock_intents_client():
    """Mock IntentsClient for tests."""
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None

    # CRUD operations
    client.create_intent = AsyncMock(return_value={
        "intent_id": "test_intent_123",
        "user_id": "user_456",
        "created_at": "2025-12-24T10:00:00Z"
    })
    client.get_intent = AsyncMock(return_value={
        "intent_id": "test_intent_123",
        "user_id": "user_456",
        "trigger_type": "scheduled",
        "enabled": True
    })
    client.update_intent = AsyncMock(return_value={
        "intent_id": "test_intent_123",
        "updated_at": "2025-12-24T11:00:00Z"
    })
    client.delete_intent = AsyncMock(return_value={"deleted": True})
    client.list_intents = AsyncMock(return_value={
        "intents": [],
        "total": 0
    })

    # Worker operations
    client.get_pending = AsyncMock(return_value={
        "pending": [],
        "count": 0
    })
    client.claim_intent = AsyncMock(return_value={
        "claimed_at": "2025-12-24T10:00:00Z",
        "claim_expires_at": "2025-12-24T10:05:00Z"
    })
    client.fire_intent = AsyncMock(return_value={
        "fired": True,
        "cooldown_active": False,
        "next_allowed_at": None
    })

    # Health check
    client.health_check = AsyncMock(return_value={"status": "ok"})

    return client


# ============================================================================
# Mock Redis Client
# ============================================================================

@pytest.fixture
def mock_redis():
    """Mock Redis client for tests."""
    redis_mock = AsyncMock()

    # Basic operations
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.setex = AsyncMock(return_value=True)
    redis_mock.delete = AsyncMock(return_value=1)
    redis_mock.exists = AsyncMock(return_value=0)
    redis_mock.expire = AsyncMock(return_value=True)

    # List operations
    redis_mock.lpush = AsyncMock(return_value=1)
    redis_mock.rpush = AsyncMock(return_value=1)
    redis_mock.lpop = AsyncMock(return_value=None)
    redis_mock.rpop = AsyncMock(return_value=None)
    redis_mock.lrange = AsyncMock(return_value=[])
    redis_mock.llen = AsyncMock(return_value=0)

    # Counter operations
    redis_mock.incr = AsyncMock(return_value=1)
    redis_mock.decr = AsyncMock(return_value=0)

    # Hash operations
    redis_mock.hget = AsyncMock(return_value=None)
    redis_mock.hset = AsyncMock(return_value=1)
    redis_mock.hgetall = AsyncMock(return_value={})
    redis_mock.hdel = AsyncMock(return_value=1)

    # Utility
    redis_mock.ping = AsyncMock(return_value=True)
    redis_mock.close = AsyncMock(return_value=None)

    return redis_mock


# ============================================================================
# Mock Telegram Bot
# ============================================================================

@pytest.fixture
def mock_telegram_bot():
    """Mock Telegram Bot for tests."""
    bot = AsyncMock()

    # Message sending
    message = Mock()
    message.message_id = 12345
    message.chat.id = 67890
    message.date = datetime.now()

    bot.send_message = AsyncMock(return_value=message)
    bot.edit_message_text = AsyncMock(return_value=message)
    bot.delete_message = AsyncMock(return_value=True)

    # Bot info
    bot.get_me = AsyncMock(return_value=Mock(
        id=123456789,
        first_name="Annie",
        username="annie_bot"
    ))

    return bot


# ============================================================================
# Mock MCP Client
# ============================================================================

@pytest.fixture
def mock_mcp_client():
    """Mock MCP client for tests."""
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None

    # Tool calling
    client.call_tool = AsyncMock(return_value={
        "content": [{"type": "text", "text": "Tool response"}]
    })

    # List tools
    client.list_tools = AsyncMock(return_value=[
        {"name": "get_portfolio", "description": "Get portfolio data"},
        {"name": "internet_search", "description": "Search the web"}
    ])

    return client


# ============================================================================
# Sample Data Fixtures
# ============================================================================

@pytest.fixture
def sample_scheduled_intent():
    """Sample scheduled intent (cron mode)."""
    return {
        "intent_id": "scheduled_intent_123",
        "user_id": "user_456",
        "trigger_type": "scheduled",
        "enabled": True,
        "schedule": {
            "mode": "cron",
            "cron_expression": "0 9 * * 1-5",  # 9am weekdays
            "timezone": "America/Los_Angeles"
        },
        "action_context": {
            "intent_summary": "Daily morning portfolio check",
            "execution_instructions": "Check portfolio and provide brief update",
            "tools_to_use": ["get_portfolio"],
            "message_guidelines": {
                "tone": "professional",
                "max_length": 150,
                "format": "brief"
            }
        },
        "created_at": "2025-12-20T10:00:00Z",
        "execution_count": 5,
        "last_executed": "2025-12-24T09:00:00Z"
    }


@pytest.fixture
def sample_once_intent():
    """Sample scheduled intent (once mode)."""
    return {
        "intent_id": "once_intent_456",
        "user_id": "user_789",
        "trigger_type": "scheduled",
        "enabled": True,
        "schedule": {
            "mode": "once",
            "execute_at": "2025-12-25T15:00:00Z",
            "timezone": "America/New_York"
        },
        "action_context": {
            "intent_summary": "Christmas market reminder",
            "execution_instructions": "Remind about checking stock market on Christmas",
            "tools_to_use": [],
            "message_guidelines": {
                "tone": "friendly",
                "max_length": 100
            }
        },
        "created_at": "2025-12-24T10:00:00Z",
        "execution_count": 0,
        "last_executed": None
    }


@pytest.fixture
def sample_price_intent():
    """Sample condition intent (price trigger)."""
    return {
        "intent_id": "price_intent_789",
        "user_id": "user_456",
        "trigger_type": "condition",
        "enabled": True,
        "condition": {
            "type": "price",
            "expression": "NVDA < 130",
            "check_interval_minutes": 5,
            "cooldown_hours": 24
        },
        "action_context": {
            "intent_summary": "Alert when NVDA drops below $130",
            "execution_instructions": "Notify user about NVDA price drop with current price",
            "tools_to_use": ["internet_search"],
            "message_guidelines": {
                "tone": "urgent",
                "max_length": 120
            }
        },
        "created_at": "2025-12-23T10:00:00Z",
        "execution_count": 2,
        "last_executed": "2025-12-23T14:00:00Z",
        "cooldown_until": None
    }


@pytest.fixture
def sample_portfolio_intent():
    """Sample condition intent (portfolio trigger)."""
    return {
        "intent_id": "portfolio_intent_101",
        "user_id": "user_456",
        "trigger_type": "condition",
        "enabled": True,
        "condition": {
            "type": "portfolio",
            "expression": "any_holding_change > 5%",
            "check_interval_minutes": 15,
            "cooldown_hours": 4
        },
        "action_context": {
            "intent_summary": "Alert on significant portfolio changes",
            "execution_instructions": "Report which holdings changed and by how much",
            "tools_to_use": ["get_portfolio"],
            "message_guidelines": {
                "tone": "informative",
                "max_length": 200
            }
        },
        "created_at": "2025-12-22T10:00:00Z",
        "execution_count": 8,
        "last_executed": "2025-12-24T08:00:00Z",
        "cooldown_until": None
    }


@pytest.fixture
def sample_silence_intent():
    """Sample condition intent (silence trigger)."""
    return {
        "intent_id": "silence_intent_202",
        "user_id": "user_456",
        "trigger_type": "condition",
        "enabled": True,
        "condition": {
            "type": "silence",
            "expression": "silence > 4h",
            "check_interval_minutes": 30,
            "cooldown_hours": 12
        },
        "action_context": {
            "intent_summary": "Check in if user hasn't messaged in 4+ hours",
            "execution_instructions": "Friendly check-in asking how user is doing",
            "tools_to_use": [],
            "message_guidelines": {
                "tone": "casual",
                "max_length": 80
            }
        },
        "created_at": "2025-12-21T10:00:00Z",
        "execution_count": 3,
        "last_executed": "2025-12-23T18:00:00Z",
        "cooldown_until": None
    }


@pytest.fixture
def sample_user_profile():
    """Sample user profile with timezone and preferences."""
    return {
        "user_id": "user_456",
        "telegram_user_id": 67890,
        "name": "Test User",
        "timezone": "America/Los_Angeles",
        "preferences": {
            "proactive_enabled": True,
            "quiet_hours_start": 22,  # 10 PM
            "quiet_hours_end": 8,     # 8 AM
            "max_daily_proactive": 5
        },
        "created_at": "2025-12-01T10:00:00Z",
        "updated_at": "2025-12-20T15:00:00Z"
    }


@pytest.fixture
def sample_opted_out_profile():
    """Sample user profile with proactive disabled."""
    return {
        "user_id": "user_opted_out",
        "telegram_user_id": 99999,
        "name": "Opted Out User",
        "timezone": "America/New_York",
        "preferences": {
            "proactive_enabled": False,  # User opted out
            "quiet_hours_start": 22,
            "quiet_hours_end": 8,
            "max_daily_proactive": 5
        },
        "created_at": "2025-12-01T10:00:00Z",
        "updated_at": "2025-12-15T12:00:00Z"
    }


# ============================================================================
# Mock LLM Client
# ============================================================================

@pytest.fixture
def mock_llm_client():
    """Mock LLM client that returns streaming responses."""

    async def mock_stream(messages, tools=None):
        """Mock streaming response."""
        yield {"type": "token", "content": "This"}
        yield {"type": "token", "content": " is"}
        yield {"type": "token", "content": " a"}
        yield {"type": "token", "content": " test"}
        yield {"type": "token", "content": " message"}
        yield {"type": "done", "tokens_used": {"prompt": 100, "completion": 10}}

    client = Mock()
    client.chat_completion_stream = mock_stream
    return client


# ============================================================================
# Utility Functions
# ============================================================================

def make_intent_response(intent_id: str, **kwargs) -> Dict[str, Any]:
    """Helper to create mock intent API responses."""
    base = {
        "intent_id": intent_id,
        "user_id": kwargs.get("user_id", "user_456"),
        "trigger_type": kwargs.get("trigger_type", "scheduled"),
        "enabled": kwargs.get("enabled", True),
        "created_at": kwargs.get("created_at", "2025-12-24T10:00:00Z"),
        "execution_count": kwargs.get("execution_count", 0),
        "last_executed": kwargs.get("last_executed", None)
    }
    base.update(kwargs)
    return base


def make_gate_result(allowed: bool = True, reason: str = None, defer_until: datetime = None) -> Dict[str, Any]:
    """Helper to create mock gate check results."""
    return {
        "allowed": allowed,
        "reason": reason,
        "defer_until": defer_until.isoformat() if defer_until else None,
        "checks_passed": [] if not allowed else ["opt_out", "recent_contact", "daily_limit", "quiet_hours"]
    }


def make_evaluator_result(met: bool = True, reason: str = "Condition met", data: Dict = None) -> Dict[str, Any]:
    """Helper to create mock evaluator results."""
    return {
        "met": met,
        "reason": reason,
        "data": data or {}
    }
