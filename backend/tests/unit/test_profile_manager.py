"""
Unit tests for ProfileManager

Tests profile caching, background refresh, and trigger logic.
"""

import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

from api.profile import ProfileManager


@pytest.fixture
async def redis_mock():
    """Mock Redis client."""
    mock = AsyncMock()
    # Old JSON string methods (still used for profile cache)
    mock.get = AsyncMock()
    mock.setex = AsyncMock()
    # New Redis Hash methods (used for profile metadata)
    mock.hgetall = AsyncMock()
    mock.hget = AsyncMock()
    mock.hincrby = AsyncMock()
    mock.hset = AsyncMock()
    mock.expire = AsyncMock()
    mock.exists = AsyncMock()
    mock.close = AsyncMock()
    return mock


@pytest.fixture
async def profile_manager(redis_mock):
    """ProfileManager instance with mocked Redis."""
    manager = ProfileManager(redis_client=redis_mock)
    return manager


@pytest.mark.asyncio
async def test_load_profile_from_cache_hit(profile_manager, redis_mock):
    """Test loading profile from cache when cached data exists."""
    user_id = "test_user_123"
    cached_profile = {
        "user_id": user_id,
        "completeness": 45,
        "basics": {"name": "Sarah", "timezone": "US/Pacific"},
        "preferences": {"communication_style": "direct"},
        "goals": {},
        "interests": {},
        "background": {}
    }

    # Mock Redis get to return cached data
    redis_mock.get.return_value = json.dumps(cached_profile)

    result = await profile_manager.load_profile_from_cache(user_id)

    # Assertions
    assert result["user_id"] == user_id
    assert result["completeness"] == 45
    assert result["cached"]
    assert result["basics"]["name"] == "Sarah"
    redis_mock.get.assert_called_once_with(f"profile:{user_id}")


@pytest.mark.asyncio
async def test_load_profile_from_cache_miss(profile_manager, redis_mock):
    """Test loading profile when cache is empty."""
    user_id = "test_user_123"

    # Mock Redis get to return None (cache miss)
    redis_mock.get.return_value = None

    result = await profile_manager.load_profile_from_cache(user_id)

    # Assertions
    assert result["user_id"] == user_id
    assert result["completeness"] == 0
    assert not result["cached"]
    assert result["basics"] == {}
    assert result["preferences"] == {}
    redis_mock.get.assert_called_once_with(f"profile:{user_id}")


@pytest.mark.asyncio
async def test_load_profile_redis_error_graceful_degradation(profile_manager, redis_mock):
    """Test graceful degradation when Redis fails."""
    user_id = "test_user_123"

    # Mock Redis to raise error
    import redis.asyncio as redis_lib
    redis_mock.get.side_effect = redis_lib.RedisError("Connection failed")

    result = await profile_manager.load_profile_from_cache(user_id)

    # Should return empty profile, not raise exception
    assert result["user_id"] == user_id
    assert result["completeness"] == 0
    assert not result["cached"]


@pytest.mark.asyncio
async def test_refresh_profile_background_success(profile_manager, redis_mock):
    """Test successful background profile refresh."""
    user_id = "test_user_123"
    mcp_response = {
        "status": "success",
        "user_id": user_id,
        "completeness": 60,
        "basics": {"name": "Sarah"},
        "preferences": {},
        "goals": {},
        "interests": {},
        "background": {}
    }

    # Mock MCP client
    with patch("api.profile.MCPClient") as mcp_mock:
        mcp_client_instance = AsyncMock()
        mcp_client_instance.call_tool = AsyncMock(return_value=mcp_response)
        mcp_mock.return_value.__aenter__.return_value = mcp_client_instance

        await profile_manager.refresh_profile_background(user_id)

        # Verify MCP tool was called
        mcp_client_instance.call_tool.assert_called_once_with(
            "get_user_profile",
            {"user_id": user_id}
        )

        # Verify profile was cached using SETEX (still uses JSON for profile cache)
        assert redis_mock.setex.call_count == 1  # profile only

        # Check profile was cached
        profile_call = redis_mock.setex.call_args_list[0]
        assert profile_call[0][0] == f"profile:{user_id}"
        assert profile_call[0][1] == 900  # TTL
        cached_data = json.loads(profile_call[0][2])
        assert cached_data["completeness"] == 60

        # Verify _update_last_refresh was called (uses HSET + EXPIRE for metadata)
        redis_mock.hset.assert_called_once()
        hset_call = redis_mock.hset.call_args[0]
        assert hset_call[0] == f"profile_meta:{user_id}"
        assert hset_call[1] == "last_refresh"
        # hset_call[2] is the timestamp string

        # Verify EXPIRE was called to set TTL on metadata
        redis_mock.expire.assert_called_once_with(f"profile_meta:{user_id}", 86400)


@pytest.mark.asyncio
async def test_refresh_profile_background_mcp_failure(profile_manager, redis_mock):
    """Test background refresh when MCP tool returns error."""
    user_id = "test_user_123"
    mcp_response = {
        "status": "error",
        "error": "Network timeout",
        "user_id": user_id
    }

    with patch("api.profile.MCPClient") as mcp_mock:
        mcp_client_instance = AsyncMock()
        mcp_client_instance.call_tool = AsyncMock(return_value=mcp_response)
        mcp_mock.return_value.__aenter__.return_value = mcp_client_instance

        # Should not raise exception - graceful handling
        await profile_manager.refresh_profile_background(user_id)

        # Verify MCP tool was called
        mcp_client_instance.call_tool.assert_called_once()

        # Profile should NOT be cached when MCP fails
        profile_calls = [call for call in redis_mock.setex.call_args_list
                         if "profile:" in call[0][0]]
        assert len(profile_calls) == 0


@pytest.mark.asyncio
async def test_check_refresh_triggers_first_time(profile_manager, redis_mock):
    """Test refresh trigger on first access (no metadata)."""
    user_id = "test_user_123"

    # Mock Redis hgetall to return empty dict (no metadata)
    redis_mock.hgetall.return_value = {}

    result = await profile_manager.check_refresh_triggers(user_id)

    assert result  # Should trigger on first time
    redis_mock.hgetall.assert_called_once_with(f"profile_meta:{user_id}")


@pytest.mark.asyncio
async def test_check_refresh_triggers_message_count(profile_manager, redis_mock):
    """Test message count trigger (every 5 messages)."""
    user_id = "test_user_123"

    # Test trigger at message 5, 10, 15, etc.
    for count in [5, 10, 15, 20]:
        # Redis Hash returns dict with string values
        metadata = {
            "message_count": str(count),
            "last_refresh": datetime.now(timezone.utc).isoformat()
        }
        redis_mock.hgetall.return_value = metadata

        result = await profile_manager.check_refresh_triggers(user_id)
        assert result, f"Should trigger at message count {count}"

    # Test NO trigger at message 4, 6, 7, 8, 9
    for count in [4, 6, 7, 8, 9]:
        # Redis Hash returns dict with string values
        metadata = {
            "message_count": str(count),
            "last_refresh": datetime.now(timezone.utc).isoformat()
        }
        redis_mock.hgetall.return_value = metadata

        result = await profile_manager.check_refresh_triggers(user_id)
        assert not result, f"Should NOT trigger at message count {count}"


@pytest.mark.asyncio
async def test_check_refresh_triggers_time_based(profile_manager, redis_mock):
    """Test time-based trigger (every 15 minutes)."""
    user_id = "test_user_123"

    # Last refresh was 16 minutes ago (should trigger)
    last_refresh = datetime.now(timezone.utc) - timedelta(minutes=16)
    # Redis Hash returns dict with string values
    metadata = {
        "message_count": "3",  # Not a message trigger
        "last_refresh": last_refresh.isoformat()
    }
    redis_mock.hgetall.return_value = metadata

    result = await profile_manager.check_refresh_triggers(user_id)
    assert result  # Should trigger based on time

    # Last refresh was 14 minutes ago (should NOT trigger)
    last_refresh = datetime.now(timezone.utc) - timedelta(minutes=14)
    metadata["last_refresh"] = last_refresh.isoformat()
    redis_mock.hgetall.return_value = metadata

    result = await profile_manager.check_refresh_triggers(user_id)
    assert not result  # Should NOT trigger yet


@pytest.mark.asyncio
async def test_increment_message_count_new_user(profile_manager, redis_mock):
    """Test incrementing message count for new user."""
    user_id = "test_user_123"

    # Mock Redis hincrby to return 1 (first increment)
    redis_mock.hincrby.return_value = 1

    count = await profile_manager.increment_message_count(user_id)

    assert count == 1

    # Verify HINCRBY was called correctly
    redis_mock.hincrby.assert_called_once_with(f"profile_meta:{user_id}", "message_count", 1)

    # Verify EXPIRE was called to set TTL
    redis_mock.expire.assert_called_once_with(f"profile_meta:{user_id}", 86400)


@pytest.mark.asyncio
async def test_increment_message_count_existing_user(profile_manager, redis_mock):
    """Test incrementing message count for existing user."""
    user_id = "test_user_123"

    # Mock Redis hincrby to return 6 (existing count 5 + 1)
    redis_mock.hincrby.return_value = 6

    count = await profile_manager.increment_message_count(user_id)

    assert count == 6

    # Verify HINCRBY was called correctly
    redis_mock.hincrby.assert_called_once_with(f"profile_meta:{user_id}", "message_count", 1)

    # Verify EXPIRE was called to reset TTL
    redis_mock.expire.assert_called_once_with(f"profile_meta:{user_id}", 86400)


@pytest.mark.asyncio
async def test_profile_manager_close(profile_manager, redis_mock):
    """Test closing ProfileManager closes Redis connection."""
    # ProfileManager was created with external Redis client (not owned)
    await profile_manager.close()

    # Should NOT close external Redis client
    redis_mock.close.assert_not_called()


@pytest.mark.asyncio
async def test_profile_manager_close_owned_redis():
    """Test closing ProfileManager closes owned Redis connection."""
    with patch("api.profile.redis.Redis") as redis_class_mock:
        redis_instance = AsyncMock()
        redis_class_mock.return_value = redis_instance

        # Create ProfileManager without providing redis_client (creates own)
        manager = ProfileManager()
        assert manager._owned_redis

        await manager.close()

        # Should close owned Redis client
        redis_instance.close.assert_called_once()
