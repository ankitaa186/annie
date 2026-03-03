"""
Integration tests for Profile Integration & Smart Caching (Story 7.1)

Tests the complete profile flow:
- Chat endpoint profile loading
- Background refresh triggers
- Profile injection into system prompt
- Graceful degradation when services unavailable

IMPORTANT: These tests require running Redis service.
"""

import asyncio
import json
import pytest
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi.testclient import TestClient

from api.main import app
from api.profile import ProfileManager
from api.state import StateManager


def check_redis_available() -> bool:
    """Check if Redis is available for e2e tests."""
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('redis', 6379))
        sock.close()
        if result == 0:
            return True
        # Try localhost as fallback
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('localhost', 6379))
        sock.close()
        return result == 0
    except Exception:
        return False


REDIS_AVAILABLE = check_redis_available()
pytestmark = pytest.mark.skipif(
    not REDIS_AVAILABLE,
    reason="Redis service not available for e2e tests"
)


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
async def redis_client():
    """Real Redis client for integration tests."""
    import redis.asyncio as redis
    client = redis.Redis(
        host="redis",
        port=6379,
        decode_responses=True
    )
    yield client
    await client.close()


@pytest.fixture
async def cleanup_redis(redis_client):
    """Clean up Redis keys after each test."""
    yield
    # Clean up all test keys
    keys = await redis_client.keys("profile:test_*")
    keys.extend(await redis_client.keys("profile_meta:test_*"))
    keys.extend(await redis_client.keys("profile_cache:*"))
    keys.extend(await redis_client.keys("session:test_*"))
    keys.extend(await redis_client.keys("conversation:*"))

    for key in keys:
        await redis_client.delete(key)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_complete_profile_flow(client, redis_client, cleanup_redis):
    """
    Test complete profile integration flow:
    1. Chat request loads profile from cache
    2. Profile stored in Redis for stream endpoint
    3. Stream endpoint loads profile and injects into system prompt
    """
    user_id = "test_user_complete_flow"

    # Setup: Pre-populate profile cache with mock data
    profile_data = {
        "user_id": user_id,
        "completeness": 60,
        "cached": True,
        "basics": {
            "name": "Alice",
            "timezone": "US/Pacific",
            "occupation": "Software Engineer"
        },
        "preferences": {
            "communication_style": "direct"
        },
        "goals": {
            "short_term_goals": "Learn AI development"
        },
        "interests": {},
        "background": {}
    }

    await redis_client.setex(
        f"profile:{user_id}",
        900,
        json.dumps(profile_data)
    )

    # Step 1: Send chat request
    response = client.post("/api/chat", json={
        "user_id": user_id,
        "platform": "telegram",
        "message": "Hello, can you help me?"
    })

    assert response.status_code == 200
    data = response.json()
    assert "conversation_id" in data
    conversation_id = data["conversation_id"]

    # Step 2: Verify profile was cached for stream endpoint
    profile_cache_key = f"profile_cache:{conversation_id}"
    cached_profile = await redis_client.get(profile_cache_key)
    assert cached_profile is not None

    profile_from_cache = json.loads(cached_profile)
    assert profile_from_cache["completeness"] == 60
    assert profile_from_cache["basics"]["name"] == "Alice"

    # Step 3: Verify message count was incremented (profile_meta is a Redis Hash)
    meta_key = f"profile_meta:{user_id}"
    metadata = await redis_client.hgetall(meta_key)
    assert metadata is not None and len(metadata) > 0

    assert int(metadata["message_count"]) == 1

    print(f"✅ Complete profile flow test passed")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_empty_profile_handling(client, redis_client, cleanup_redis):
    """
    Test that empty profiles are handled gracefully (new user).
    """
    user_id = "test_user_new"

    # No profile in cache - simulates new user

    # Send chat request
    response = client.post("/api/chat", json={
        "user_id": user_id,
        "platform": "telegram",
        "message": "First message"
    })

    assert response.status_code == 200
    data = response.json()
    conversation_id = data["conversation_id"]

    # Verify empty profile was NOT cached (completeness == 0)
    profile_cache_key = f"profile_cache:{conversation_id}"
    cached_profile = await redis_client.get(profile_cache_key)
    # Should be None since completeness is 0
    assert cached_profile is None

    # Verify message count was still incremented (profile_meta is a Redis Hash)
    meta_key = f"profile_meta:{user_id}"
    metadata = await redis_client.hgetall(meta_key)
    assert metadata is not None and len(metadata) > 0

    assert int(metadata["message_count"]) == 1

    print(f"✅ Empty profile handling test passed")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_message_count_trigger(client, redis_client, cleanup_redis):
    """
    Test that background refresh is triggered every 5 messages.
    """
    user_id = "test_user_message_trigger"

    # Setup: Pre-populate profile cache
    profile_data = {
        "user_id": user_id,
        "completeness": 45,
        "cached": True,
        "basics": {"name": "Bob"},
        "preferences": {},
        "goals": {},
        "interests": {},
        "background": {}
    }

    await redis_client.setex(
        f"profile:{user_id}",
        900,
        json.dumps(profile_data)
    )

    # Send 5 messages to trigger refresh
    for i in range(5):
        response = client.post("/api/chat", json={
            "user_id": user_id,
            "platform": "telegram",
            "message": f"Message {i+1}"
        })
        assert response.status_code == 200

        # Small delay to avoid race conditions
        await asyncio.sleep(0.1)

    # Verify message count is 5 (profile_meta is a Redis Hash)
    meta_key = f"profile_meta:{user_id}"
    metadata = await redis_client.hgetall(meta_key)
    assert int(metadata["message_count"]) == 5

    # Note: We can't easily verify background refresh was triggered in test,
    # but we verified the trigger logic returns True in unit tests

    print(f"✅ Message count trigger test passed")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_profile_manager_refresh_with_mcp(redis_client, cleanup_redis):
    """
    Test ProfileManager background refresh with mocked MCP client.
    """
    user_id = "test_user_mcp_refresh"

    # Mock MCP response
    mcp_response = {
        "status": "success",
        "user_id": user_id,
        "completeness": 75,
        "basics": {
            "name": "Charlie",
            "age": 30,
            "timezone": "US/Eastern"
        },
        "preferences": {
            "communication_style": "friendly"
        },
        "goals": {},
        "interests": {},
        "background": {}
    }

    # Create ProfileManager and refresh profile
    with patch("api.profile.MCPClient") as mcp_mock:
        mcp_client_instance = AsyncMock()
        mcp_client_instance.call_tool = AsyncMock(return_value=mcp_response)
        mcp_mock.return_value.__aenter__.return_value = mcp_client_instance

        profile_manager = ProfileManager(redis_client=redis_client)
        await profile_manager.refresh_profile_background(user_id)

    # Verify profile was cached
    profile_key = f"profile:{user_id}"
    cached_profile = await redis_client.get(profile_key)
    assert cached_profile is not None

    profile = json.loads(cached_profile)
    assert profile["completeness"] == 75
    assert profile["basics"]["name"] == "Charlie"
    assert profile["basics"]["age"] == 30

    # Verify metadata was updated with last_refresh (profile_meta is a Redis Hash)
    meta_key = f"profile_meta:{user_id}"
    metadata = await redis_client.hgetall(meta_key)
    assert metadata is not None and len(metadata) > 0

    assert metadata.get("last_refresh") is not None

    # Verify last_refresh is recent (within last 5 seconds)
    last_refresh = datetime.fromisoformat(metadata["last_refresh"])
    time_diff = datetime.now(timezone.utc) - last_refresh
    assert time_diff.total_seconds() < 5

    print(f"✅ ProfileManager refresh with MCP test passed")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_profile_injection_in_prompt():
    """
    Test that profile is correctly formatted and injected into system prompt.
    """
    from api.prompts import build_system_prompt, format_profile_for_prompt

    # Test profile data
    profile = {
        "user_id": "test_user_prompt",
        "completeness": 80,
        "basics": {
            "name": "Diana",
            "age": 28,
            "occupation": "Data Scientist",
            "timezone": "US/Pacific"
        },
        "preferences": {
            "communication_style": "casual",
            "language": "English"
        },
        "goals": {
            "short_term_goals": "Master machine learning",
            "values": "Innovation and learning"
        },
        "interests": {
            "hobbies": "Reading, hiking"
        },
        "background": {}
    }

    # Test profile formatting
    formatted_profile = format_profile_for_prompt(profile)
    assert formatted_profile is not None
    assert "Profile Completeness: 80%" in formatted_profile
    assert "Name: Diana" in formatted_profile
    assert "Occupation: Data Scientist" in formatted_profile
    assert "Communication Style: casual" in formatted_profile
    assert "Short-term Goals: Master machine learning" in formatted_profile

    # Test system prompt with profile
    system_prompt = build_system_prompt(
        user_id="test_user_prompt",
        platform="telegram",
        include_tool_instructions=True,
        profile=profile
    )

    assert "USER PROFILE:" in system_prompt
    assert "Diana" in system_prompt
    assert "Data Scientist" in system_prompt
    assert "Profile Completeness: 80%" in system_prompt

    print(f"✅ Profile injection in prompt test passed")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_graceful_degradation_profile_error(client, redis_client, cleanup_redis):
    """
    Test graceful degradation when profile loading fails.
    """
    user_id = "test_user_error"

    # Simulate Redis error by mocking ProfileManager to raise exception
    with patch("api.routes.chat.ProfileManager") as profile_mock:
        profile_mock.side_effect = Exception("Redis connection failed")

        # Chat request should still succeed
        response = client.post("/api/chat", json={
            "user_id": user_id,
            "platform": "telegram",
            "message": "Test message"
        })

        # Should succeed despite profile error
        assert response.status_code == 200
        data = response.json()
        assert "conversation_id" in data

    print(f"✅ Graceful degradation test passed")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_time_based_trigger(redis_client, cleanup_redis):
    """
    Test time-based refresh trigger (15 minutes).
    """
    user_id = "test_user_time_trigger"

    # Setup metadata with last_refresh > 15 minutes ago using Redis Hash
    # (check_refresh_triggers uses hgetall/hget, not get/json)
    old_refresh = datetime.now(timezone.utc) - timedelta(minutes=16)
    meta_key = f"profile_meta:{user_id}"

    await redis_client.hset(meta_key, mapping={
        "message_count": "3",  # Not a message count trigger
        "last_refresh": old_refresh.isoformat()
    })
    await redis_client.expire(meta_key, 86400)

    # Check if trigger fires
    profile_manager = ProfileManager(redis_client=redis_client)
    should_refresh = await profile_manager.check_refresh_triggers(user_id)

    assert should_refresh == True

    # Test with recent refresh (should NOT trigger)
    recent_refresh = datetime.now(timezone.utc) - timedelta(minutes=10)

    await redis_client.hset(meta_key, "last_refresh", recent_refresh.isoformat())
    await redis_client.expire(meta_key, 86400)

    should_refresh = await profile_manager.check_refresh_triggers(user_id)
    assert should_refresh == False

    print(f"✅ Time-based trigger test passed")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_empty_profile_skips_injection():
    """
    Test that empty profile (completeness=0) skips USER PROFILE section.
    """
    from api.prompts import build_system_prompt

    # Empty profile
    empty_profile = {
        "user_id": "test_user_empty",
        "completeness": 0,
        "cached": False,
        "basics": {},
        "preferences": {},
        "goals": {},
        "interests": {},
        "background": {}
    }

    # Build system prompt
    system_prompt = build_system_prompt(
        user_id="test_user_empty",
        platform="api",
        profile=empty_profile
    )

    # Should NOT contain USER PROFILE section
    assert "USER PROFILE:" not in system_prompt

    # Should still contain user_id
    assert "test_user_empty" in system_prompt

    print(f"✅ Empty profile skips injection test passed")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s", "-m", "integration"])
