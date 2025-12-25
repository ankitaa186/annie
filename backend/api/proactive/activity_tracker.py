"""
Activity Tracker Module

Tracks user activity timestamps for silence detection and gate checks.
Part of the Proactive AI Worker infrastructure.

Redis Key Patterns:
- activity:{user_id}:last_message -> ISO timestamp (TTL: 7 days)

Usage:
    from api.proactive.activity_tracker import ActivityTracker

    # In chat endpoint
    async with ActivityTracker() as tracker:
        await tracker.record_activity(user_id)

    # In gate/evaluator
    async with ActivityTracker() as tracker:
        hours = await tracker.get_hours_since_activity(user_id)
        if hours and hours > 24:
            # User has been silent for 24+ hours
"""

from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as redis
from redis import exceptions as redis_exceptions

from api.config import get_config
from api.logging import get_logger

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

# TTL for activity tracking: 7 days in seconds
ACTIVITY_TTL = 604800


class ActivityTracker:
    """
    Activity Tracker for user activity timestamps.

    Tracks when users last interacted with the system to support:
    - Silence detection (for proactive outreach)
    - Recent contact checks (for spam prevention)
    - Activity-based trigger evaluation

    Features:
    - Redis-backed timestamp storage
    - 7-day TTL for automatic cleanup
    - Graceful error handling (never breaks chat flow)
    - Context manager support for resource management
    """

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """
        Initialize ActivityTracker.

        Args:
            redis_client: Optional Redis client. If not provided, creates new connection.
                         Recommended to pass from StateManager to reuse connection.
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
            logger.debug(f"ActivityTracker created Redis connection to {redis_host}:{redis_port}")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def close(self):
        """Close Redis connection if owned by this tracker."""
        if self._owned_redis and self.redis_client:
            await self.redis_client.close()
            logger.debug("ActivityTracker closed owned Redis connection")

    @observe(name="activity_record", as_type="span")
    async def record_activity(self, user_id: str, activity_type: str = "message") -> None:
        """
        Record user activity timestamp.

        Stores ISO timestamp in Redis with 7-day TTL.
        Non-blocking, fire-and-forget operation that never raises exceptions.

        Args:
            user_id: User identifier (Telegram user ID)
            activity_type: Type of activity (default: "message")

        Example:
            async with ActivityTracker() as tracker:
                await tracker.record_activity("123456")
        """
        try:
            key = f"activity:{user_id}:last_message"
            timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

            await self.redis_client.setex(key, ACTIVITY_TTL, timestamp)

            logger.info(
                "User activity recorded",
                extra={
                    "user_id": user_id,
                    "activity_type": activity_type,
                    "timestamp": timestamp,
                    "key": key,
                    "ttl": ACTIVITY_TTL
                }
            )

        except redis_exceptions.ConnectionError as e:
            logger.warning(
                f"Failed to record activity (Redis unavailable): {str(e)}",
                extra={
                    "user_id": user_id,
                    "error_type": "ConnectionError"
                }
            )
        except redis_exceptions.RedisError as e:
            logger.warning(
                f"Failed to record activity (Redis error): {str(e)}",
                extra={
                    "user_id": user_id,
                    "error_type": type(e).__name__
                }
            )
        except Exception as e:
            logger.error(
                f"Unexpected error recording activity: {str(e)}",
                extra={
                    "user_id": user_id,
                    "error_type": type(e).__name__
                },
                exc_info=True
            )

    @observe(name="activity_get_last", as_type="span")
    async def get_last_activity(self, user_id: str) -> Optional[datetime]:
        """
        Get last activity timestamp for user.

        Returns datetime object or None if no activity found.
        Handles missing keys gracefully (returns None for new users).

        Args:
            user_id: User identifier (Telegram user ID)

        Returns:
            datetime object with UTC timezone, or None if not found

        Example:
            async with ActivityTracker() as tracker:
                last_active = await tracker.get_last_activity("123456")
                if last_active:
                    print(f"Last active: {last_active.isoformat()}")
                else:
                    print("New user, no activity recorded")
        """
        try:
            key = f"activity:{user_id}:last_message"
            timestamp_str = await self.redis_client.get(key)

            if timestamp_str is None:
                logger.debug(
                    "No activity found for user (new user or expired)",
                    extra={"user_id": user_id}
                )
                return None

            # Parse ISO timestamp string to datetime object
            # Handle Z suffix (2025-12-24T10:30:00Z)
            dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))

            logger.debug(
                "Retrieved user activity",
                extra={
                    "user_id": user_id,
                    "timestamp": timestamp_str,
                    "key": key
                }
            )

            return dt

        except redis_exceptions.ConnectionError as e:
            logger.warning(
                f"Failed to get activity (Redis unavailable): {str(e)}",
                extra={
                    "user_id": user_id,
                    "error_type": "ConnectionError"
                }
            )
            return None
        except redis_exceptions.RedisError as e:
            logger.warning(
                f"Failed to get activity (Redis error): {str(e)}",
                extra={
                    "user_id": user_id,
                    "error_type": type(e).__name__
                }
            )
            return None
        except (ValueError, TypeError) as e:
            logger.error(
                f"Failed to parse activity timestamp: {str(e)}",
                extra={
                    "user_id": user_id,
                    "error_type": type(e).__name__
                },
                exc_info=True
            )
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error getting activity: {str(e)}",
                extra={
                    "user_id": user_id,
                    "error_type": type(e).__name__
                },
                exc_info=True
            )
            return None

    @observe(name="activity_hours_since", as_type="span")
    async def get_hours_since_activity(self, user_id: str) -> Optional[float]:
        """
        Calculate hours since last activity.

        Returns float representing hours, or None if no activity found.

        Args:
            user_id: User identifier (Telegram user ID)

        Returns:
            Hours since last activity (float), or None if no activity

        Example:
            async with ActivityTracker() as tracker:
                hours = await tracker.get_hours_since_activity("123456")
                if hours:
                    print(f"User silent for {hours:.1f} hours")
                else:
                    print("New user, no activity history")
        """
        last_activity = await self.get_last_activity(user_id)

        if last_activity is None:
            return None

        now = datetime.now(timezone.utc)
        delta = now - last_activity
        hours = delta.total_seconds() / 3600

        logger.debug(
            "Calculated hours since activity",
            extra={
                "user_id": user_id,
                "hours": round(hours, 2),
                "last_activity": last_activity.isoformat()
            }
        )

        return hours

    @observe(name="activity_is_active", as_type="span")
    async def is_user_active(self, user_id: str, within_hours: float) -> bool:
        """
        Check if user was active within specified time window.

        Args:
            user_id: User identifier (Telegram user ID)
            within_hours: Time window in hours (e.g., 1.0 for "within last hour")

        Returns:
            True if user was active within window, False otherwise

        Example:
            async with ActivityTracker() as tracker:
                # Check if user was active in last hour
                if await tracker.is_user_active("123456", within_hours=1.0):
                    print("User recently active, skip proactive message")
        """
        hours = await self.get_hours_since_activity(user_id)

        if hours is None:
            # New user, no activity history
            return False

        is_active = hours <= within_hours

        logger.debug(
            "Checked user activity status",
            extra={
                "user_id": user_id,
                "within_hours": within_hours,
                "hours_since_activity": round(hours, 2),
                "is_active": is_active
            }
        )

        return is_active
