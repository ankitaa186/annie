"""
Tests for Proactive Feedback Handler - Closed-loop learning.

Tests:
- Detecting proactive message context
- Feedback window validation
- Missing/malformed data handling
- Graceful degradation on errors
"""

import pytest
import json
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timedelta, timezone
from freezegun import freeze_time

from api.proactive.feedback import get_proactive_context


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    return AsyncMock()


@pytest.fixture
def sample_proactive_message():
    """Sample proactive message data stored in Redis."""
    return {
        "trigger_id": "trigger_123",
        "message_id": "msg_456",
        "sent_at": datetime.now(timezone.utc).isoformat()
    }


# ============================================================================
# Proactive Context Detection Tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_proactive_context_no_message(mock_redis):
    """Test returns None when no proactive message exists."""
    mock_redis.get = AsyncMock(return_value=None)

    result = await get_proactive_context("user_123", mock_redis)

    assert result is None
    mock_redis.get.assert_called_once_with("proactive_message:user_123:last")


@pytest.mark.asyncio
async def test_get_proactive_context_valid_message(mock_redis, sample_proactive_message):
    """Test returns context when valid proactive message exists."""
    mock_redis.get = AsyncMock(return_value=json.dumps(sample_proactive_message))

    with patch('api.proactive.feedback.IntentsClient') as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get_trigger = AsyncMock(return_value={
            "id": "trigger_123",
            "intent_name": "Daily Briefing",
            "trigger_type": "cron"
        })
        mock_client.return_value = mock_instance

        result = await get_proactive_context("user_123", mock_redis)

        assert result is not None
        assert result["trigger_id"] == "trigger_123"
        assert result["message_id"] == "msg_456"
        assert "trigger_details" in result


@pytest.mark.asyncio
async def test_get_proactive_context_outside_window(mock_redis):
    """Test returns None when message is outside 2-hour window."""
    # Message sent 3 hours ago
    old_message = {
        "trigger_id": "trigger_123",
        "message_id": "msg_456",
        "sent_at": (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    }
    mock_redis.get = AsyncMock(return_value=json.dumps(old_message))

    result = await get_proactive_context("user_123", mock_redis)

    assert result is None


@pytest.mark.asyncio
async def test_get_proactive_context_within_window(mock_redis):
    """Test returns context when message is within 2-hour window."""
    # Message sent 1 hour ago
    recent_message = {
        "trigger_id": "trigger_123",
        "message_id": "msg_456",
        "sent_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    }
    mock_redis.get = AsyncMock(return_value=json.dumps(recent_message))

    with patch('api.proactive.feedback.IntentsClient') as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get_trigger = AsyncMock(return_value={
            "id": "trigger_123",
            "intent_name": "Test"
        })
        mock_client.return_value = mock_instance

        result = await get_proactive_context("user_123", mock_redis)

        assert result is not None
        assert result["time_since_message_seconds"] < 7200  # 2 hours


@pytest.mark.asyncio
async def test_get_proactive_context_invalid_json(mock_redis):
    """Test returns None when Redis contains invalid JSON."""
    mock_redis.get = AsyncMock(return_value="not valid json {{{")

    result = await get_proactive_context("user_123", mock_redis)

    assert result is None


@pytest.mark.asyncio
async def test_get_proactive_context_missing_fields(mock_redis):
    """Test returns None when required fields are missing."""
    incomplete_message = {
        "trigger_id": "trigger_123"
        # Missing message_id and sent_at
    }
    mock_redis.get = AsyncMock(return_value=json.dumps(incomplete_message))

    result = await get_proactive_context("user_123", mock_redis)

    assert result is None


@pytest.mark.asyncio
async def test_get_proactive_context_invalid_timestamp(mock_redis):
    """Test returns None when sent_at timestamp is invalid."""
    bad_message = {
        "trigger_id": "trigger_123",
        "message_id": "msg_456",
        "sent_at": "not-a-timestamp"
    }
    mock_redis.get = AsyncMock(return_value=json.dumps(bad_message))

    result = await get_proactive_context("user_123", mock_redis)

    assert result is None


@pytest.mark.asyncio
async def test_get_proactive_context_trigger_not_found(mock_redis, sample_proactive_message):
    """Test returns partial context when trigger not found in agentic-memories."""
    mock_redis.get = AsyncMock(return_value=json.dumps(sample_proactive_message))

    with patch('api.proactive.feedback.IntentsClient') as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get_trigger = AsyncMock(return_value=None)
        mock_client.return_value = mock_instance

        result = await get_proactive_context("user_123", mock_redis)

        # Should return None when trigger not found
        assert result is None


@pytest.mark.asyncio
async def test_get_proactive_context_api_error(mock_redis, sample_proactive_message):
    """Test returns partial context when agentic-memories API fails."""
    mock_redis.get = AsyncMock(return_value=json.dumps(sample_proactive_message))

    with patch('api.proactive.feedback.IntentsClient') as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get_trigger = AsyncMock(side_effect=Exception("API Error"))
        mock_client.return_value = mock_instance

        result = await get_proactive_context("user_123", mock_redis)

        # Should still return context with partial trigger details
        assert result is not None
        assert result["trigger_id"] == "trigger_123"
        assert result["trigger_details"]["intent_name"] == "Unknown"


@pytest.mark.asyncio
async def test_get_proactive_context_redis_error(mock_redis):
    """Test returns None gracefully on Redis error."""
    mock_redis.get = AsyncMock(side_effect=Exception("Redis connection failed"))

    result = await get_proactive_context("user_123", mock_redis)

    assert result is None


@pytest.mark.asyncio
async def test_get_proactive_context_includes_time_diff(mock_redis, sample_proactive_message):
    """Test returned context includes time_since_message_seconds."""
    mock_redis.get = AsyncMock(return_value=json.dumps(sample_proactive_message))

    with patch('api.proactive.feedback.IntentsClient') as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get_trigger = AsyncMock(return_value={"id": "trigger_123"})
        mock_client.return_value = mock_instance

        result = await get_proactive_context("user_123", mock_redis)

        assert result is not None
        assert "time_since_message_seconds" in result
        assert isinstance(result["time_since_message_seconds"], float)
