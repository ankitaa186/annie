"""
Subconscious Gate for Proactive Messages

Spam prevention layer that checks multiple conditions before allowing
proactive messages to be sent to users.

Gate Checks (in fail-fast order):
1. User opt-out - Check proactive_enabled preference
2. Recent contact - Block if user messaged < 1 hour ago
3. Daily limit - Block if >= 5 proactive messages today
4. Quiet hours - Block if 22:00 - 08:00 in user's timezone

Redis Key Patterns:
- session:{user_id} - Contains last_activity timestamp
- proactive:{user_id}:daily:{YYYY-MM-DD} - Daily message counter (TTL: 24h)
- profile:{user_id} - User profile with timezone and preferences
"""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import pytz
import redis.asyncio as redis

from api.config import get_config
from api.logging import get_logger
from api.profile import ProfileManager

try:
    from langfuse.decorators import observe
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False
    def observe(**kwargs):
        def decorator(func):
            return func
        return decorator

logger = get_logger(__name__)


@dataclass
class GateResult:
    """Result from subconscious gate check.

    Attributes:
        allowed: Whether the proactive message is allowed
        reason: Reason for blocking (None if allowed)
        defer_until: When to retry if blocked by quiet hours (None otherwise)
        checks_passed: List of check names that passed
    """
    allowed: bool
    reason: Optional[str] = None
    defer_until: Optional[datetime] = None
    checks_passed: List[str] = None

    def __post_init__(self):
        """Initialize checks_passed list if not provided."""
        if self.checks_passed is None:
            self.checks_passed = []


class GateError(Exception):
    """Base exception for gate errors."""
    pass


class SubconsciousGate:
    """
    Spam prevention gate for proactive messages.

    Checks multiple conditions before allowing proactive messages:
    1. User opt-out - Check proactive_enabled in profile
    2. Recent contact - Block if user messaged < 1 hour ago
    3. Daily limit - Block if >= 5 proactive messages today
    4. Quiet hours - Block if 22:00 - 08:00 in user's timezone

    Returns GateResult with allowed flag and optional reason/defer_until.

    Usage:
        gate = SubconsciousGate()
        result = await gate.should_fire(trigger, user_id)

        if result.allowed:
            # Send message
            await gate.increment_daily_count(user_id)
        else:
            logger.info(f"Gate blocked: {result.reason}")
    """

    # Configuration
    RECENT_CONTACT_HOURS = 1
    DAILY_MESSAGE_LIMIT = 5
    QUIET_HOURS_START = 22  # 10 PM
    QUIET_HOURS_END = 8     # 8 AM
    DAILY_COUNTER_TTL = 86400  # 24 hours

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """
        Initialize SubconsciousGate.

        Args:
            redis_client: Optional Redis client. If not provided, creates new connection.
        """
        self.config = get_config()
        self.redis_client = redis_client
        self._owned_redis = False

        if self.redis_client is None:
            # Create Redis connection if not provided
            redis_host = self.config.get("REDIS_HOST", "redis")
            redis_port = int(self.config.get("REDIS_PORT", 6379))
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                decode_responses=True
            )
            self._owned_redis = True
            logger.debug(
                "SubconsciousGate created Redis connection",
                extra={"redis_host": redis_host, "redis_port": redis_port}
            )

        # Create ProfileManager for user profile access
        self.profile_manager = ProfileManager(redis_client=self.redis_client)

    async def close(self):
        """Close Redis connection if owned by this gate."""
        if self._owned_redis and self.redis_client:
            await self.redis_client.close()
            logger.debug("SubconsciousGate closed Redis connection")

    @observe(name="subconscious_gate_check", as_type="span")
    async def should_fire(self, trigger: dict, user_id: str) -> GateResult:
        """
        Main entry point - check if proactive message should be sent.

        Runs all gate checks in fail-fast order (cheapest to most expensive):
        1. User opt-out (single profile read)
        2. Recent contact (single session read)
        3. Daily limit (single Redis read)
        4. Quiet hours (requires timezone calculation)

        Returns first blocking result or allowed=True if all pass.

        Note: Runs ALL checks even if one fails (for debugging/logging),
        but returns on first blocking result to fail fast.

        Args:
            trigger: Trigger object (for logging/debugging)
            user_id: User identifier

        Returns:
            GateResult with allowed flag, optional reason, and checks_passed list
        """
        checks_passed = []

        try:
            # Check 1: User opt-out (fastest - single profile read)
            result = await self._check_opt_out(user_id)
            if result:
                logger.info(
                    "Gate blocked by user opt-out",
                    extra={
                        "user_id": user_id,
                        "trigger_id": trigger.get("id"),
                        "trigger_type": trigger.get("trigger_type"),
                        "checks_passed": checks_passed,
                    }
                )
                return result
            checks_passed.append("opt_out")

            # Check 2: Recent contact (single session read)
            result = await self._check_recent_contact(user_id)
            if result:
                logger.info(
                    "Gate blocked by recent contact",
                    extra={
                        "user_id": user_id,
                        "trigger_id": trigger.get("id"),
                        "trigger_type": trigger.get("trigger_type"),
                        "checks_passed": checks_passed,
                    }
                )
                return result
            checks_passed.append("recent_contact")

            # Check 3: Daily limit (single Redis read)
            result = await self._check_daily_limit(user_id)
            if result:
                logger.info(
                    "Gate blocked by daily limit",
                    extra={
                        "user_id": user_id,
                        "trigger_id": trigger.get("id"),
                        "trigger_type": trigger.get("trigger_type"),
                        "checks_passed": checks_passed,
                    }
                )
                return result
            checks_passed.append("daily_limit")

            # Check 4: Quiet hours (requires timezone calculation)
            result = await self._check_quiet_hours(user_id)
            if result:
                logger.info(
                    "Gate blocked by quiet hours",
                    extra={
                        "user_id": user_id,
                        "trigger_id": trigger.get("id"),
                        "trigger_type": trigger.get("trigger_type"),
                        "defer_until": result.defer_until.isoformat() if result.defer_until else None,
                        "checks_passed": checks_passed,
                    }
                )
                return result
            checks_passed.append("quiet_hours")

            # All checks passed
            logger.info(
                "Gate allowed proactive message",
                extra={
                    "user_id": user_id,
                    "trigger_id": trigger.get("id"),
                    "trigger_type": trigger.get("trigger_type"),
                    "checks_passed": checks_passed,
                }
            )
            return GateResult(allowed=True, checks_passed=checks_passed)

        except Exception as e:
            # On error, block to prevent spam (fail-safe)
            logger.error(
                "Gate check error - blocking to prevent spam",
                extra={
                    "user_id": user_id,
                    "trigger_id": trigger.get("id"),
                    "error": str(e),
                    "checks_passed": checks_passed,
                }
            )
            return GateResult(
                allowed=False,
                reason="error",
                checks_passed=checks_passed
            )

    async def _check_opt_out(self, user_id: str) -> Optional[GateResult]:
        """
        Check if user has disabled proactive messages.

        Args:
            user_id: User identifier

        Returns:
            GateResult if blocked, None if allowed
        """
        try:
            # Load user profile (uses cache, very fast)
            profile = await self.profile_manager.load_profile_from_cache(user_id)

            # Check proactive_enabled preference
            # Default to True (enabled) if not explicitly set
            proactive_enabled = profile.get("preferences", {}).get("proactive_enabled", True)

            if proactive_enabled is False:
                logger.debug(
                    "User has disabled proactive messages",
                    extra={"user_id": user_id}
                )
                return GateResult(allowed=False, reason="user_opt_out")

            return None

        except Exception as e:
            # On error, allow (fail open for this check - user preference error shouldn't block)
            logger.warning(
                "Error checking user opt-out - allowing",
                extra={"user_id": user_id, "error": str(e)}
            )
            return None

    async def _check_recent_contact(self, user_id: str) -> Optional[GateResult]:
        """
        Check if user messaged within the last hour.

        Args:
            user_id: User identifier

        Returns:
            GateResult if blocked, None if allowed
        """
        try:
            # Read session to get last_activity
            session_key = f"session:{user_id}"
            session_json = await self.redis_client.get(session_key)

            if not session_json:
                # No session = no recent activity
                logger.debug(
                    "No session found - allowing (no recent contact)",
                    extra={"user_id": user_id}
                )
                return None

            # Parse session JSON
            session = json.loads(session_json)
            last_activity_str = session.get("last_activity")

            if not last_activity_str:
                # No last_activity in session
                logger.debug(
                    "No last_activity in session - allowing",
                    extra={"user_id": user_id}
                )
                return None

            # Parse timestamp: "2025-12-24T10:30:00Z"
            last_activity = datetime.fromisoformat(last_activity_str.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            time_since = now - last_activity

            # Check if less than 1 hour ago
            if time_since < timedelta(hours=self.RECENT_CONTACT_HOURS):
                hours_since = time_since.total_seconds() / 3600
                logger.debug(
                    "Recent contact detected - blocking",
                    extra={
                        "user_id": user_id,
                        "last_activity": last_activity_str,
                        "hours_since": round(hours_since, 2),
                    }
                )
                return GateResult(allowed=False, reason="recent_contact")

            return None

        except Exception as e:
            # On error, allow (fail open - session errors shouldn't block)
            logger.warning(
                "Error checking recent contact - allowing",
                extra={"user_id": user_id, "error": str(e)}
            )
            return None

    async def _check_daily_limit(self, user_id: str) -> Optional[GateResult]:
        """
        Check if daily message limit has been reached.

        Args:
            user_id: User identifier

        Returns:
            GateResult if blocked, None if allowed
        """
        try:
            # Get today's date in UTC
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            counter_key = f"proactive:{user_id}:daily:{today}"

            # Read current count
            count_str = await self.redis_client.get(counter_key)

            if not count_str:
                # No count = 0 messages today
                logger.debug(
                    "No daily count - allowing",
                    extra={"user_id": user_id, "date": today}
                )
                return None

            current_count = int(count_str)

            # Check if at or over limit
            if current_count >= self.DAILY_MESSAGE_LIMIT:
                logger.debug(
                    "Daily limit reached - blocking",
                    extra={
                        "user_id": user_id,
                        "current_count": current_count,
                        "limit": self.DAILY_MESSAGE_LIMIT,
                        "date": today,
                    }
                )
                return GateResult(allowed=False, reason="daily_limit")

            logger.debug(
                "Under daily limit - allowing",
                extra={
                    "user_id": user_id,
                    "current_count": current_count,
                    "limit": self.DAILY_MESSAGE_LIMIT,
                    "date": today,
                }
            )
            return None

        except Exception as e:
            # On error, block to prevent spam (fail-safe)
            logger.error(
                "Error checking daily limit - blocking to prevent spam",
                extra={"user_id": user_id, "error": str(e)}
            )
            return GateResult(allowed=False, reason="error")

    async def _check_quiet_hours(self, user_id: str) -> Optional[GateResult]:
        """
        Check if current time is in quiet hours (22:00 - 08:00 user local time).

        Args:
            user_id: User identifier

        Returns:
            GateResult with defer_until if blocked, None if allowed
        """
        try:
            # Load user profile for timezone
            profile = await self.profile_manager.load_profile_from_cache(user_id)

            # Get timezone from profile, default to UTC
            timezone_str = profile.get("basics", {}).get("timezone", "UTC")

            try:
                user_tz = pytz.timezone(timezone_str)
            except (pytz.exceptions.UnknownTimeZoneError, ValueError, KeyError) as e:
                logger.warning(
                    "Invalid timezone in profile - falling back to UTC",
                    extra={
                        "user_id": user_id,
                        "timezone": timezone_str,
                        "error": str(e),
                    }
                )
                user_tz = pytz.UTC

            # Get current time in user's timezone
            user_now = datetime.now(user_tz)
            user_hour = user_now.hour

            # Check if in quiet hours (22:00 - 08:00)
            if self.QUIET_HOURS_START <= user_hour or user_hour < self.QUIET_HOURS_END:
                # Calculate next 8 AM
                if user_hour >= self.QUIET_HOURS_START:
                    # After 10 PM - defer to 8 AM tomorrow
                    next_8am = user_now.replace(hour=8, minute=0, second=0, microsecond=0)
                    next_8am += timedelta(days=1)
                else:
                    # Before 8 AM - defer to 8 AM today
                    next_8am = user_now.replace(hour=8, minute=0, second=0, microsecond=0)

                logger.debug(
                    "Quiet hours detected - blocking",
                    extra={
                        "user_id": user_id,
                        "user_hour": user_hour,
                        "timezone": timezone_str,
                        "defer_until": next_8am.isoformat(),
                    }
                )

                return GateResult(
                    allowed=False,
                    reason="quiet_hours",
                    defer_until=next_8am
                )

            logger.debug(
                "Outside quiet hours - allowing",
                extra={
                    "user_id": user_id,
                    "user_hour": user_hour,
                    "timezone": timezone_str,
                }
            )
            return None

        except Exception as e:
            # On error, allow (fail open - timezone errors shouldn't block)
            logger.warning(
                "Error checking quiet hours - allowing",
                extra={"user_id": user_id, "error": str(e)}
            )
            return None

    @observe(name="increment_daily_count", as_type="span")
    async def increment_daily_count(self, user_id: str) -> int:
        """
        Increment daily proactive message count.

        Should be called AFTER successful message delivery (not during gate check).

        Args:
            user_id: User identifier

        Returns:
            New count value
        """
        try:
            # Get today's date in UTC
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            counter_key = f"proactive:{user_id}:daily:{today}"

            # Increment counter
            new_count = await self.redis_client.incr(counter_key)

            # Set TTL on first increment
            if new_count == 1:
                await self.redis_client.expire(counter_key, self.DAILY_COUNTER_TTL)
                logger.debug(
                    "Created daily counter with TTL",
                    extra={
                        "user_id": user_id,
                        "date": today,
                        "ttl": self.DAILY_COUNTER_TTL,
                    }
                )

            logger.info(
                "Incremented daily proactive count",
                extra={
                    "user_id": user_id,
                    "date": today,
                    "new_count": new_count,
                    "limit": self.DAILY_MESSAGE_LIMIT,
                }
            )

            return new_count

        except Exception as e:
            logger.error(
                "Error incrementing daily count",
                extra={"user_id": user_id, "error": str(e)}
            )
            raise GateError(f"Failed to increment daily count: {e}")
