"""
Tests for TelegramDelivery - Sending proactive messages via Telegram.

Tests:
- DeliveryResult dataclass
- Sending messages successfully
- Rate limit handling
- Error handling (Telegram API errors)
- Message recording for feedback
"""

import pytest
import json
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime

from api.proactive.telegram_delivery import (
    TelegramDelivery,
    DeliveryResult,
    record_proactive_message,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    return AsyncMock()


@pytest.fixture
def mock_bot():
    """Mock Telegram Bot."""
    bot = AsyncMock()
    return bot


# ============================================================================
# DeliveryResult Tests
# ============================================================================

def test_delivery_result_success():
    """Test DeliveryResult for successful delivery."""
    result = DeliveryResult(
        success=True,
        message_id="12345",
        error=None,
        delivery_ms=150
    )

    assert result.success is True
    assert result.message_id == "12345"
    assert result.error is None
    assert result.delivery_ms == 150


def test_delivery_result_failure():
    """Test DeliveryResult for failed delivery."""
    result = DeliveryResult(
        success=False,
        message_id=None,
        error="Rate limited",
        delivery_ms=500
    )

    assert result.success is False
    assert result.message_id is None
    assert result.error == "Rate limited"
    assert result.delivery_ms == 500


# ============================================================================
# TelegramDelivery Initialization Tests
# ============================================================================

def test_telegram_delivery_init_with_token(mock_redis):
    """Test TelegramDelivery initialization with explicit token."""
    with patch('api.proactive.telegram_delivery.Bot') as mock_bot_class:
        delivery = TelegramDelivery(
            bot_token="test_token_123",
            redis_client=mock_redis
        )

        mock_bot_class.assert_called_once_with(token="test_token_123")
        assert delivery.redis_client is mock_redis


def test_telegram_delivery_init_missing_token_raises():
    """Test TelegramDelivery raises when token missing."""
    with patch('api.proactive.telegram_delivery.get_config') as mock_config:
        mock_config.return_value = {"TELEGRAM_BOT_TOKEN": "REPLACE_ME"}

        with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN is required"):
            TelegramDelivery()


# ============================================================================
# Send Message Tests
# ============================================================================

@pytest.mark.asyncio
async def test_send_proactive_message_success(mock_redis):
    """Test successful message delivery."""
    with patch('api.proactive.telegram_delivery.Bot') as mock_bot_class:
        # Setup mock
        mock_bot = AsyncMock()
        mock_message = Mock()
        mock_message.message_id = 12345
        mock_bot.send_message = AsyncMock(return_value=mock_message)
        mock_bot_class.return_value = mock_bot

        delivery = TelegramDelivery(
            bot_token="test_token",
            redis_client=mock_redis
        )

        result = await delivery.send_proactive_message(
            user_id="123456789",
            message="Hello from Annie!",
            trigger_id="trigger_abc"
        )

        assert result.success is True
        assert result.message_id == "12345"
        assert result.error is None
        mock_bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_send_proactive_message_empty_user_id(mock_redis):
    """Test validation error for empty user_id."""
    with patch('api.proactive.telegram_delivery.Bot') as mock_bot_class:
        delivery = TelegramDelivery(
            bot_token="test_token",
            redis_client=mock_redis
        )

        result = await delivery.send_proactive_message(
            user_id="",
            message="Hello!",
            trigger_id="trigger_abc"
        )

        assert result.success is False
        assert "empty" in result.error.lower() or "user_id" in result.error.lower()


@pytest.mark.asyncio
async def test_send_proactive_message_empty_message(mock_redis):
    """Test validation error for empty message."""
    with patch('api.proactive.telegram_delivery.Bot') as mock_bot_class:
        delivery = TelegramDelivery(
            bot_token="test_token",
            redis_client=mock_redis
        )

        result = await delivery.send_proactive_message(
            user_id="123456789",
            message="",
            trigger_id="trigger_abc"
        )

        assert result.success is False
        assert "empty" in result.error.lower() or "message" in result.error.lower()


@pytest.mark.asyncio
async def test_send_proactive_message_invalid_user_id(mock_redis):
    """Test validation error for non-numeric user_id."""
    with patch('api.proactive.telegram_delivery.Bot') as mock_bot_class:
        delivery = TelegramDelivery(
            bot_token="test_token",
            redis_client=mock_redis
        )

        result = await delivery.send_proactive_message(
            user_id="not-a-number",
            message="Hello!",
            trigger_id="trigger_abc"
        )

        assert result.success is False
        assert "invalid" in result.error.lower() or "numeric" in result.error.lower()


@pytest.mark.asyncio
async def test_send_proactive_message_rate_limited(mock_redis):
    """Test rate limit handling with retry."""
    from telegram.error import RetryAfter

    with patch('api.proactive.telegram_delivery.Bot') as mock_bot_class:
        mock_bot = AsyncMock()

        # First call raises RetryAfter, second succeeds
        mock_message = Mock()
        mock_message.message_id = 12345
        mock_bot.send_message = AsyncMock(
            side_effect=[RetryAfter(1), mock_message]
        )
        mock_bot_class.return_value = mock_bot

        delivery = TelegramDelivery(
            bot_token="test_token",
            redis_client=mock_redis
        )

        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await delivery.send_proactive_message(
                user_id="123456789",
                message="Hello!",
                trigger_id="trigger_abc"
            )

        assert result.success is True
        assert mock_bot.send_message.call_count == 2


@pytest.mark.asyncio
async def test_send_proactive_message_telegram_error(mock_redis):
    """Test handling of Telegram API errors."""
    from telegram.error import TelegramError

    with patch('api.proactive.telegram_delivery.Bot') as mock_bot_class:
        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock(
            side_effect=TelegramError("Chat not found")
        )
        mock_bot_class.return_value = mock_bot

        delivery = TelegramDelivery(
            bot_token="test_token",
            redis_client=mock_redis
        )

        result = await delivery.send_proactive_message(
            user_id="123456789",
            message="Hello!",
            trigger_id="trigger_abc"
        )

        assert result.success is False
        assert "error" in result.error.lower() or "telegram" in result.error.lower()


# ============================================================================
# Record Message Tests
# ============================================================================

@pytest.mark.asyncio
async def test_record_proactive_message(mock_redis):
    """Test recording proactive message in Redis."""
    mock_redis.setex = AsyncMock()

    await record_proactive_message(
        redis_client=mock_redis,
        user_id="user_123",
        trigger_id="trigger_abc",
        message_id="msg_456"
    )

    mock_redis.setex.assert_called_once()
    call_args = mock_redis.setex.call_args

    # Check key format
    assert call_args[0][0] == "proactive_message:user_123:last"

    # Check TTL (2 hours = 7200 seconds)
    assert call_args[0][1] == 7200

    # Check stored data
    stored_data = json.loads(call_args[0][2])
    assert stored_data["trigger_id"] == "trigger_abc"
    assert stored_data["message_id"] == "msg_456"
    assert "sent_at" in stored_data


@pytest.mark.asyncio
async def test_record_proactive_message_redis_error(mock_redis):
    """Test record_proactive_message handles Redis errors."""
    mock_redis.setex = AsyncMock(side_effect=Exception("Redis error"))

    # Should raise since it's the caller's responsibility to handle
    with pytest.raises(Exception, match="Redis error"):
        await record_proactive_message(
            redis_client=mock_redis,
            user_id="user_123",
            trigger_id="trigger_abc",
            message_id="msg_456"
        )
