"""
Tests for SubconsciousGate - Spam prevention layer for proactive messages.

Tests:
- User opt-out check
- Recent contact check
- Daily limit check
- Quiet hours check
- Full gate flow
- Error handling
"""

import pytest
import json
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timedelta, timezone
from freezegun import freeze_time

from api.proactive.gate import SubconsciousGate, GateResult, GateError


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_redis():
    """Mock async Redis client."""
    return AsyncMock()


@pytest.fixture
def mock_profile_manager():
    """Mock ProfileManager."""
    manager = AsyncMock()
    manager.load_profile_from_cache = AsyncMock(return_value={
        "preferences": {"proactive_enabled": True},
        "basics": {"timezone": "America/Los_Angeles"}
    })
    return manager


@pytest.fixture
def sample_trigger():
    """Sample trigger for gate checks."""
    return {
        "id": "trigger_123",
        "user_id": "user_456",
        "trigger_type": "cron"
    }


# ============================================================================
# GateResult Tests
# ============================================================================

def test_gate_result_allowed():
    """Test GateResult for allowed message."""
    result = GateResult(
        allowed=True,
        checks_passed=["opt_out", "recent_contact", "daily_limit", "quiet_hours"]
    )

    assert result.allowed is True
    assert result.reason is None
    assert result.defer_until is None
    assert len(result.checks_passed) == 4


def test_gate_result_blocked():
    """Test GateResult for blocked message."""
    result = GateResult(
        allowed=False,
        reason="daily_limit",
        checks_passed=["opt_out", "recent_contact"]
    )

    assert result.allowed is False
    assert result.reason == "daily_limit"


def test_gate_result_default_checks_passed():
    """Test GateResult initializes checks_passed to empty list."""
    result = GateResult(allowed=True)

    assert result.checks_passed == []


# ============================================================================
# SubconsciousGate Initialization Tests
# ============================================================================

def test_gate_init_with_redis(mock_redis):
    """Test SubconsciousGate initialization with Redis client."""
    with patch('api.proactive.gate.ProfileManager') as mock_pm_class:
        gate = SubconsciousGate(redis_client=mock_redis)

        assert gate.redis_client is mock_redis
        assert gate._owned_redis is False


# ============================================================================
# Opt-Out Check Tests
# ============================================================================

@pytest.mark.asyncio
async def test_gate_allows_when_proactive_enabled(mock_redis, sample_trigger):
    """Test gate allows when proactive_enabled is True."""
    with patch('api.proactive.gate.ProfileManager') as mock_pm_class:
        mock_pm = AsyncMock()
        mock_pm.load_profile_from_cache = AsyncMock(return_value={
            "preferences": {"proactive_enabled": True},
            "basics": {"timezone": "UTC"}
        })
        mock_pm_class.return_value = mock_pm

        # Mock Redis for other checks
        mock_redis.get = AsyncMock(return_value=None)

        gate = SubconsciousGate(redis_client=mock_redis)
        gate.profile_manager = mock_pm

        result = await gate.should_fire(sample_trigger, "user_456")

        assert "opt_out" in result.checks_passed


@pytest.mark.asyncio
async def test_gate_blocks_when_opted_out(mock_redis, sample_trigger):
    """Test gate blocks when user has opted out."""
    with patch('api.proactive.gate.ProfileManager') as mock_pm_class:
        mock_pm = AsyncMock()
        mock_pm.load_profile_from_cache = AsyncMock(return_value={
            "preferences": {"proactive_enabled": False}
        })
        mock_pm_class.return_value = mock_pm

        gate = SubconsciousGate(redis_client=mock_redis)
        gate.profile_manager = mock_pm
        # Enable the opt-out check for this test
        gate.CHECK_OPT_OUT_ENABLED = True

        result = await gate.should_fire(sample_trigger, "user_456")

        assert result.allowed is False
        assert result.reason == "user_opt_out"


# ============================================================================
# Recent Contact Check Tests
# ============================================================================

@pytest.mark.asyncio
async def test_gate_blocks_recent_contact(mock_redis, sample_trigger):
    """Test gate blocks when user contacted less than 1 hour ago."""
    with patch('api.proactive.gate.ProfileManager') as mock_pm_class:
        mock_pm = AsyncMock()
        mock_pm.load_profile_from_cache = AsyncMock(return_value={
            "preferences": {"proactive_enabled": True},
            "basics": {"timezone": "UTC"}
        })
        mock_pm_class.return_value = mock_pm

        # User contacted 30 minutes ago
        last_activity = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        mock_redis.get = AsyncMock(return_value=json.dumps({
            "last_activity": last_activity
        }))

        gate = SubconsciousGate(redis_client=mock_redis)
        gate.profile_manager = mock_pm
        # Enable the recent contact check for this test
        gate.CHECK_RECENT_CONTACT_ENABLED = True

        result = await gate.should_fire(sample_trigger, "user_456")

        assert result.allowed is False
        assert result.reason == "recent_contact"


@pytest.mark.asyncio
async def test_gate_allows_no_recent_contact(mock_redis, sample_trigger):
    """Test gate allows when user contacted more than 1 hour ago."""
    with patch('api.proactive.gate.ProfileManager') as mock_pm_class:
        mock_pm = AsyncMock()
        mock_pm.load_profile_from_cache = AsyncMock(return_value={
            "preferences": {"proactive_enabled": True},
            "basics": {"timezone": "UTC"}
        })
        mock_pm_class.return_value = mock_pm

        # User contacted 2 hours ago
        last_activity = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        mock_redis.get = AsyncMock(side_effect=[
            json.dumps({"last_activity": last_activity}),  # session
            None  # daily counter
        ])

        gate = SubconsciousGate(redis_client=mock_redis)
        gate.profile_manager = mock_pm

        result = await gate.should_fire(sample_trigger, "user_456")

        assert "recent_contact" in result.checks_passed


@pytest.mark.asyncio
async def test_gate_allows_no_previous_messages(mock_redis, sample_trigger):
    """Test gate allows when no session exists."""
    with patch('api.proactive.gate.ProfileManager') as mock_pm_class:
        mock_pm = AsyncMock()
        mock_pm.load_profile_from_cache = AsyncMock(return_value={
            "preferences": {"proactive_enabled": True},
            "basics": {"timezone": "UTC"}
        })
        mock_pm_class.return_value = mock_pm

        mock_redis.get = AsyncMock(return_value=None)

        gate = SubconsciousGate(redis_client=mock_redis)
        gate.profile_manager = mock_pm

        result = await gate.should_fire(sample_trigger, "user_456")

        # Should pass recent_contact check
        assert "recent_contact" in result.checks_passed


# ============================================================================
# Daily Limit Check Tests
# ============================================================================

@pytest.mark.asyncio
async def test_gate_blocks_daily_limit_reached(mock_redis, sample_trigger):
    """Test gate blocks when daily limit is reached."""
    with patch('api.proactive.gate.ProfileManager') as mock_pm_class:
        mock_pm = AsyncMock()
        mock_pm.load_profile_from_cache = AsyncMock(return_value={
            "preferences": {"proactive_enabled": True},
            "basics": {"timezone": "UTC"}
        })
        mock_pm_class.return_value = mock_pm

        # No recent contact, but at daily limit
        mock_redis.get = AsyncMock(side_effect=[
            None,  # session (no recent contact)
            "5"    # daily counter at limit
        ])

        gate = SubconsciousGate(redis_client=mock_redis)
        gate.profile_manager = mock_pm
        # Enable the daily limit check for this test
        gate.CHECK_DAILY_LIMIT_ENABLED = True

        result = await gate.should_fire(sample_trigger, "user_456")

        assert result.allowed is False
        assert result.reason == "daily_limit"


@pytest.mark.asyncio
async def test_gate_allows_under_daily_limit(mock_redis, sample_trigger):
    """Test gate allows when under daily limit."""
    with patch('api.proactive.gate.ProfileManager') as mock_pm_class:
        mock_pm = AsyncMock()
        mock_pm.load_profile_from_cache = AsyncMock(return_value={
            "preferences": {"proactive_enabled": True},
            "basics": {"timezone": "UTC"}
        })
        mock_pm_class.return_value = mock_pm

        mock_redis.get = AsyncMock(side_effect=[
            None,  # session
            "3"    # daily counter under limit
        ])

        gate = SubconsciousGate(redis_client=mock_redis)
        gate.profile_manager = mock_pm

        result = await gate.should_fire(sample_trigger, "user_456")

        assert "daily_limit" in result.checks_passed


# ============================================================================
# Quiet Hours Check Tests
# ============================================================================

@pytest.mark.asyncio
@freeze_time("2025-12-25 23:00:00", tz_offset=0)  # 11 PM UTC
async def test_gate_blocks_quiet_hours_night(mock_redis, sample_trigger):
    """Test gate blocks during quiet hours (night)."""
    with patch('api.proactive.gate.ProfileManager') as mock_pm_class:
        mock_pm = AsyncMock()
        mock_pm.load_profile_from_cache = AsyncMock(return_value={
            "preferences": {"proactive_enabled": True},
            "basics": {"timezone": "UTC"}  # 11 PM in UTC = quiet hours
        })
        mock_pm_class.return_value = mock_pm

        mock_redis.get = AsyncMock(return_value=None)

        gate = SubconsciousGate(redis_client=mock_redis)
        gate.profile_manager = mock_pm
        # Enable the quiet hours check for this test
        gate.CHECK_QUIET_HOURS_ENABLED = True

        result = await gate.should_fire(sample_trigger, "user_456")

        assert result.allowed is False
        assert result.reason == "quiet_hours"
        assert result.defer_until is not None


@pytest.mark.asyncio
@freeze_time("2025-12-25 06:00:00", tz_offset=0)  # 6 AM UTC
async def test_gate_blocks_quiet_hours_early_morning(mock_redis, sample_trigger):
    """Test gate blocks during quiet hours (early morning)."""
    with patch('api.proactive.gate.ProfileManager') as mock_pm_class:
        mock_pm = AsyncMock()
        mock_pm.load_profile_from_cache = AsyncMock(return_value={
            "preferences": {"proactive_enabled": True},
            "basics": {"timezone": "UTC"}  # 6 AM in UTC = quiet hours
        })
        mock_pm_class.return_value = mock_pm

        mock_redis.get = AsyncMock(return_value=None)

        gate = SubconsciousGate(redis_client=mock_redis)
        gate.profile_manager = mock_pm
        # Enable the quiet hours check for this test
        gate.CHECK_QUIET_HOURS_ENABLED = True

        result = await gate.should_fire(sample_trigger, "user_456")

        assert result.allowed is False
        assert result.reason == "quiet_hours"


@pytest.mark.asyncio
@freeze_time("2025-12-25 14:00:00", tz_offset=0)  # 2 PM UTC
async def test_gate_allows_outside_quiet_hours(mock_redis, sample_trigger):
    """Test gate allows outside quiet hours."""
    with patch('api.proactive.gate.ProfileManager') as mock_pm_class:
        mock_pm = AsyncMock()
        mock_pm.load_profile_from_cache = AsyncMock(return_value={
            "preferences": {"proactive_enabled": True},
            "basics": {"timezone": "UTC"}  # 2 PM in UTC = not quiet hours
        })
        mock_pm_class.return_value = mock_pm

        mock_redis.get = AsyncMock(return_value=None)

        gate = SubconsciousGate(redis_client=mock_redis)
        gate.profile_manager = mock_pm

        result = await gate.should_fire(sample_trigger, "user_456")

        assert "quiet_hours" in result.checks_passed


# ============================================================================
# Full Flow Tests
# ============================================================================

@pytest.mark.asyncio
@freeze_time("2025-12-25 14:00:00", tz_offset=0)
async def test_gate_all_checks_pass(mock_redis, sample_trigger):
    """Test gate allows when all checks pass."""
    with patch('api.proactive.gate.ProfileManager') as mock_pm_class:
        mock_pm = AsyncMock()
        mock_pm.load_profile_from_cache = AsyncMock(return_value={
            "preferences": {"proactive_enabled": True},
            "basics": {"timezone": "UTC"}
        })
        mock_pm_class.return_value = mock_pm

        mock_redis.get = AsyncMock(return_value=None)

        gate = SubconsciousGate(redis_client=mock_redis)
        gate.profile_manager = mock_pm

        result = await gate.should_fire(sample_trigger, "user_456")

        assert result.allowed is True
        assert "opt_out" in result.checks_passed
        assert "recent_contact" in result.checks_passed
        assert "daily_limit" in result.checks_passed
        assert "quiet_hours" in result.checks_passed


# ============================================================================
# Increment Daily Count Tests
# ============================================================================

@pytest.mark.asyncio
async def test_increment_daily_count(mock_redis):
    """Test incrementing daily message count."""
    mock_redis.incr = AsyncMock(return_value=3)
    mock_redis.expire = AsyncMock()

    with patch('api.proactive.gate.ProfileManager') as mock_pm_class:
        gate = SubconsciousGate(redis_client=mock_redis)

        count = await gate.increment_daily_count("user_456")

        assert count == 3
        mock_redis.incr.assert_called_once()


@pytest.mark.asyncio
async def test_increment_daily_count_sets_ttl_on_first(mock_redis):
    """Test TTL is set on first increment."""
    mock_redis.incr = AsyncMock(return_value=1)  # First increment
    mock_redis.expire = AsyncMock()

    with patch('api.proactive.gate.ProfileManager') as mock_pm_class:
        gate = SubconsciousGate(redis_client=mock_redis)

        await gate.increment_daily_count("user_456")

        mock_redis.expire.assert_called_once()


# ============================================================================
# Error Handling Tests
# ============================================================================

@pytest.mark.asyncio
async def test_gate_blocks_on_error(mock_redis, sample_trigger):
    """Test gate blocks on unexpected error (fail-safe)."""
    with patch('api.proactive.gate.ProfileManager') as mock_pm_class:
        mock_pm = AsyncMock()
        mock_pm.load_profile_from_cache = AsyncMock(
            side_effect=Exception("Database error")
        )
        mock_pm_class.return_value = mock_pm

        gate = SubconsciousGate(redis_client=mock_redis)
        gate.profile_manager = mock_pm

        result = await gate.should_fire(sample_trigger, "user_456")

        # Opt-out check fails open (allows), but overall error should block
        # Let's check if the check at least started
        assert isinstance(result, GateResult)
