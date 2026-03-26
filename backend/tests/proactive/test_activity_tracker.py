"""
Tests for ActivityTracker - User activity tracking for silence detection.

Tests:
- Recording activity timestamps
- Getting last activity
- Calculating hours since activity
- Checking if user is active within time window
- Error handling (Redis errors, invalid timestamps)
- TTL expiration behavior
"""

import pytest
from unittest.mock import AsyncMock
from datetime import datetime, timedelta, timezone
from freezegun import freeze_time

from api.proactive.activity_tracker import (
    ActivityTracker,
    ACTIVITY_TTL
)


# ============================================================================
# Initialization Tests
# ============================================================================

def test_activity_tracker_init():
    """Test ActivityTracker initialization."""
    tracker = ActivityTracker()

    assert tracker.redis_client is not None
    assert tracker._owned_redis is True


def test_activity_tracker_init_with_redis_client(mock_redis):
    """Test ActivityTracker initialization with provided Redis client."""
    tracker = ActivityTracker(redis_client=mock_redis)

    assert tracker.redis_client is mock_redis
    assert tracker._owned_redis is False


@pytest.mark.asyncio
async def test_activity_tracker_context_manager(mock_redis):
    """Test ActivityTracker works as async context manager."""
    async with ActivityTracker(redis_client=mock_redis) as tracker:
        assert tracker is not None


# ============================================================================
# Record Activity Tests
# ============================================================================

@freeze_time("2025-12-24 10:00:00")
@pytest.mark.asyncio
async def test_record_activity(mock_redis):
    """Test recording user activity."""
    tracker = ActivityTracker(redis_client=mock_redis)

    await tracker.record_activity("user_456")

    # Verify setex was called with correct key, TTL, and timestamp
    mock_redis.setex.assert_called_once()
    call_args = mock_redis.setex.call_args[0]

    assert call_args[0] == "activity:user_456:last_message"
    assert call_args[1] == ACTIVITY_TTL  # 7 days
    assert "2025-12-24T10:00:00Z" in call_args[2]


@pytest.mark.asyncio
async def test_record_activity_with_type(mock_redis):
    """Test recording activity with custom activity type."""
    tracker = ActivityTracker(redis_client=mock_redis)

    await tracker.record_activity("user_456", activity_type="command")

    # Should still use setex for timestamp storage
    mock_redis.setex.assert_called_once()


@pytest.mark.asyncio
async def test_record_activity_redis_error(mock_redis):
    """Test record_activity handles Redis errors gracefully (no exception raised)."""
    from redis import exceptions as redis_exceptions

    mock_redis.setex = AsyncMock(side_effect=redis_exceptions.RedisError("Connection failed"))

    tracker = ActivityTracker(redis_client=mock_redis)

    # Should not raise exception (fire-and-forget)
    await tracker.record_activity("user_456")

    # Operation should have been attempted
    mock_redis.setex.assert_called_once()


@pytest.mark.asyncio
async def test_record_activity_connection_error(mock_redis):
    """Test record_activity handles connection errors gracefully."""
    from redis import exceptions as redis_exceptions

    mock_redis.setex = AsyncMock(side_effect=redis_exceptions.ConnectionError("Redis unavailable"))

    tracker = ActivityTracker(redis_client=mock_redis)

    # Should not raise exception
    await tracker.record_activity("user_456")


# ============================================================================
# Get Last Activity Tests
# ============================================================================

@freeze_time("2025-12-24 10:00:00")
@pytest.mark.asyncio
async def test_get_last_activity(mock_redis):
    """Test getting last activity timestamp."""
    tracker = ActivityTracker(redis_client=mock_redis)

    # Mock Redis returning a timestamp from 2 hours ago
    timestamp = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    mock_redis.get = AsyncMock(return_value=timestamp)

    result = await tracker.get_last_activity("user_456")

    assert result is not None
    assert isinstance(result, datetime)

    # Verify it's the correct timestamp (2 hours ago)
    expected = datetime.now(timezone.utc) - timedelta(hours=2)
    assert abs((result - expected).total_seconds()) < 1  # Within 1 second


@pytest.mark.asyncio
async def test_get_last_activity_no_record(mock_redis):
    """Test getting last activity when no record exists (new user)."""
    tracker = ActivityTracker(redis_client=mock_redis)

    mock_redis.get = AsyncMock(return_value=None)

    result = await tracker.get_last_activity("user_456")

    assert result is None


@pytest.mark.asyncio
async def test_get_last_activity_invalid_timestamp(mock_redis):
    """Test getting last activity with invalid timestamp (returns None)."""
    tracker = ActivityTracker(redis_client=mock_redis)

    mock_redis.get = AsyncMock(return_value="INVALID_TIMESTAMP")

    result = await tracker.get_last_activity("user_456")

    # Should handle parse error gracefully
    assert result is None


@pytest.mark.asyncio
async def test_get_last_activity_redis_error(mock_redis):
    """Test get_last_activity handles Redis errors gracefully."""
    from redis import exceptions as redis_exceptions

    tracker = ActivityTracker(redis_client=mock_redis)

    mock_redis.get = AsyncMock(side_effect=redis_exceptions.RedisError("Connection failed"))

    result = await tracker.get_last_activity("user_456")

    # Should return None on error
    assert result is None


# ============================================================================
# Get Hours Since Activity Tests
# ============================================================================

@freeze_time("2025-12-24 10:00:00")
@pytest.mark.asyncio
async def test_get_hours_since_activity(mock_redis):
    """Test calculating hours since last activity."""
    tracker = ActivityTracker(redis_client=mock_redis)

    # Last activity was 3 hours ago
    timestamp = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat().replace("+00:00", "Z")
    mock_redis.get = AsyncMock(return_value=timestamp)

    hours = await tracker.get_hours_since_activity("user_456")

    assert hours is not None
    assert abs(hours - 3.0) < 0.01  # Should be approximately 3 hours


@freeze_time("2025-12-24 10:00:00")
@pytest.mark.asyncio
async def test_get_hours_since_activity_30_minutes(mock_redis):
    """Test hours since activity for recent activity (30 minutes)."""
    tracker = ActivityTracker(redis_client=mock_redis)

    # Last activity was 30 minutes ago
    timestamp = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
    mock_redis.get = AsyncMock(return_value=timestamp)

    hours = await tracker.get_hours_since_activity("user_456")

    assert hours is not None
    assert abs(hours - 0.5) < 0.01  # 30 minutes = 0.5 hours


@pytest.mark.asyncio
async def test_get_hours_since_activity_no_record(mock_redis):
    """Test hours since activity when no record exists."""
    tracker = ActivityTracker(redis_client=mock_redis)

    mock_redis.get = AsyncMock(return_value=None)

    hours = await tracker.get_hours_since_activity("user_456")

    assert hours is None


# ============================================================================
# Is User Active Tests
# ============================================================================

@freeze_time("2025-12-24 10:00:00")
@pytest.mark.asyncio
async def test_is_user_active_within_window(mock_redis):
    """Test is_user_active returns True when user was active within window."""
    tracker = ActivityTracker(redis_client=mock_redis)

    # Last activity was 30 minutes ago
    timestamp = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
    mock_redis.get = AsyncMock(return_value=timestamp)

    # Check if active within last 1 hour
    is_active = await tracker.is_user_active("user_456", within_hours=1.0)

    assert is_active is True


@freeze_time("2025-12-24 10:00:00")
@pytest.mark.asyncio
async def test_is_user_active_outside_window(mock_redis):
    """Test is_user_active returns False when user was active outside window."""
    tracker = ActivityTracker(redis_client=mock_redis)

    # Last activity was 2 hours ago
    timestamp = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    mock_redis.get = AsyncMock(return_value=timestamp)

    # Check if active within last 1 hour
    is_active = await tracker.is_user_active("user_456", within_hours=1.0)

    assert is_active is False


@freeze_time("2025-12-24 10:00:00")
@pytest.mark.asyncio
async def test_is_user_active_exactly_at_boundary(mock_redis):
    """Test is_user_active at exact boundary (1 hour)."""
    tracker = ActivityTracker(redis_client=mock_redis)

    # Last activity was exactly 1 hour ago
    timestamp = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    mock_redis.get = AsyncMock(return_value=timestamp)

    # Check if active within last 1 hour (should be True, <= check)
    is_active = await tracker.is_user_active("user_456", within_hours=1.0)

    assert is_active is True


@pytest.mark.asyncio
async def test_is_user_active_no_record(mock_redis):
    """Test is_user_active returns False when no activity record exists."""
    tracker = ActivityTracker(redis_client=mock_redis)

    mock_redis.get = AsyncMock(return_value=None)

    is_active = await tracker.is_user_active("user_456", within_hours=1.0)

    # New user with no history is considered not active
    assert is_active is False


@freeze_time("2025-12-24 10:00:00")
@pytest.mark.asyncio
async def test_is_user_active_multiple_windows(mock_redis):
    """Test is_user_active with different time windows."""
    tracker = ActivityTracker(redis_client=mock_redis)

    # Last activity was 3 hours ago
    timestamp = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat().replace("+00:00", "Z")
    mock_redis.get = AsyncMock(return_value=timestamp)

    # Not active within 1 hour
    assert await tracker.is_user_active("user_456", within_hours=1.0) is False

    # Not active within 2 hours
    assert await tracker.is_user_active("user_456", within_hours=2.0) is False

    # Active within 4 hours
    assert await tracker.is_user_active("user_456", within_hours=4.0) is True


# ============================================================================
# Context Manager Tests
# ============================================================================

@pytest.mark.asyncio
async def test_context_manager_closes_owned_redis():
    """Test context manager closes Redis connection if owned."""
    mock_redis = AsyncMock()
    mock_redis.close = AsyncMock()

    tracker = ActivityTracker()
    tracker.redis_client = mock_redis
    tracker._owned_redis = True

    async with tracker:
        pass

    # Should close owned connection
    mock_redis.close.assert_called_once()


@pytest.mark.asyncio
async def test_context_manager_doesnt_close_provided_redis(mock_redis):
    """Test context manager doesn't close provided Redis connection."""
    mock_redis.close = AsyncMock()

    async with ActivityTracker(redis_client=mock_redis):
        pass

    # Should NOT close provided connection
    mock_redis.close.assert_not_called()


# ============================================================================
# TTL Tests
# ============================================================================

@pytest.mark.asyncio
async def test_activity_ttl_is_seven_days():
    """Test activity TTL is set to 7 days."""
    assert ACTIVITY_TTL == 604800  # 7 days in seconds


@freeze_time("2025-12-24 10:00:00")
@pytest.mark.asyncio
async def test_record_activity_sets_ttl(mock_redis):
    """Test record_activity sets correct TTL."""
    tracker = ActivityTracker(redis_client=mock_redis)

    await tracker.record_activity("user_456")

    # Verify TTL was set to 7 days
    call_args = mock_redis.setex.call_args[0]
    assert call_args[1] == ACTIVITY_TTL


# ============================================================================
# Key Format Tests
# ============================================================================

@pytest.mark.asyncio
async def test_activity_key_format(mock_redis):
    """Test activity keys follow correct format."""
    tracker = ActivityTracker(redis_client=mock_redis)

    await tracker.record_activity("user_123")

    # Verify key format
    call_args = mock_redis.setex.call_args[0]
    assert call_args[0] == "activity:user_123:last_message"


@pytest.mark.asyncio
async def test_get_activity_key_format(mock_redis):
    """Test get_last_activity uses correct key format."""
    tracker = ActivityTracker(redis_client=mock_redis)

    mock_redis.get = AsyncMock(return_value=None)

    await tracker.get_last_activity("user_789")

    # Verify get was called with correct key
    mock_redis.get.assert_called_once_with("activity:user_789:last_message")
