"""
Profile Management Module

Redis-based user profile management with smart caching and background refresh.
Integrates with agentic-memories profile API for automatic profile extraction.

Redis Key Patterns:
- profile:{user_id} -> Profile data (JSON, TTL: 900s = 15 min)
- profile_meta:{user_id} -> Metadata: message_count, last_refresh (JSON, TTL: 86400s = 24h)

Background Refresh Triggers:
- Every 5 messages from user (message_count % 5 == 0)
- Every 15 minutes (time since last_refresh > 15 min)
- Whichever comes first
"""

import json
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

import redis.asyncio as redis

from api.config import get_config
from api.logging import get_logger
from api.mcp_client import MCPClient

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


class ProfileError(Exception):
    """Base exception for profile management errors."""
    pass


class ProfileCacheError(ProfileError):
    """Exception raised when Redis cache operations fail."""
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        self.message = message
        self.original_error = original_error
        super().__init__(message)


class ProfileManager:
    """
    Async Redis-based profile manager with smart caching and background refresh.

    Features:
    - Non-blocking cache-first profile loading (<10ms)
    - Smart background refresh (every 5 messages OR 15 minutes)
    - Graceful degradation (uses expired cache if service unavailable)
    - Automatic trigger detection for background refresh

    Redis Keys:
    - profile:{user_id} - Cached profile data (TTL: 900s)
    - profile_meta:{user_id} - Metadata (message_count, last_refresh) (TTL: 86400s)
    """

    # Cache TTL: 15 minutes (900 seconds)
    PROFILE_CACHE_TTL = 900

    # Metadata TTL: 24 hours (86400 seconds)
    PROFILE_META_TTL = 86400

    # Refresh triggers
    MESSAGE_COUNT_TRIGGER = 5  # Refresh every 5 messages
    TIME_TRIGGER_MINUTES = 15  # Refresh every 15 minutes

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """
        Initialize ProfileManager.

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
            logger.debug(f"Created Redis connection to {redis_host}:{redis_port}")

    async def close(self):
        """Close Redis connection if owned by this manager."""
        if self._owned_redis and self.redis_client:
            await self.redis_client.close()
            logger.debug("Closed Redis connection")

    @observe(name="profile_cache_load", as_type="span")
    async def load_profile_from_cache(self, user_id: str) -> Dict[str, Any]:
        """
        Load user profile from Redis cache (non-blocking, <10ms).

        Note: Called from within chat request - should nest as span.

        Returns cached profile if available, empty profile if not cached.
        Never blocks - always returns immediately.

        Args:
            user_id: User identifier

        Returns:
            dict: Profile object with all fields, or empty profile if not cached

        Example return (cached):
            {
                "user_id": "123456",
                "completeness": 45,
                "cached": true,
                "basics": {"name": "Sarah", "timezone": "US/Pacific", ...},
                "preferences": {...},
                "goals": {...},
                "interests": {...},
                "background": {...}
            }

        Example return (empty):
            {
                "user_id": "123456",
                "completeness": 0,
                "cached": false,
                "basics": {},
                "preferences": {},
                "goals": {},
                "interests": {},
                "background": {}
            }
        """
        start_time = time.time()

        try:
            cache_key = f"profile:{user_id}"
            cached_data = await self.redis_client.get(cache_key)

            duration_ms = int((time.time() - start_time) * 1000)

            if cached_data:
                profile = json.loads(cached_data)
                profile["cached"] = True

                logger.info(
                    "Profile loaded from cache",
                    extra={
                        "user_id": user_id,
                        "completeness": profile.get("completeness", 0),
                        "duration_ms": duration_ms,
                        "cache_hit": True
                    }
                )

                return profile
            else:
                # Return empty profile - background refresh will populate it
                empty_profile = {
                    "user_id": user_id,
                    "completeness": 0,
                    "cached": False,
                    "basics": {},
                    "preferences": {},
                    "goals": {},
                    "interests": {},
                    "background": {},
                    "health": {},
                    "personality": {},
                    "values": {}
                }

                logger.info(
                    "Profile cache miss - returning empty profile",
                    extra={
                        "user_id": user_id,
                        "duration_ms": duration_ms,
                        "cache_hit": False
                    }
                )

                return empty_profile

        except redis.RedisError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                f"Redis error loading profile cache: {str(e)}",
                extra={
                    "user_id": user_id,
                    "duration_ms": duration_ms,
                    "error_type": type(e).__name__
                }
            )
            # Return empty profile - graceful degradation
            return {
                "user_id": user_id,
                "completeness": 0,
                "cached": False,
                "basics": {},
                "preferences": {},
                "goals": {},
                "interests": {},
                "background": {},
                "health": {},
                "personality": {},
                "values": {}
            }

    @observe(name="profile_refresh", as_type="trace")
    async def refresh_profile_background(self, user_id: str) -> None:
        """
        Refresh profile from agentic-memories and update Redis cache.

        Note: Runs as background task (separate trace). Link to user via metadata.

        This is designed to run as a background task - non-blocking.
        Calls get_user_profile MCP tool, updates cache with TTL=900s,
        and updates metadata.

        Args:
            user_id: User identifier
        """
        start_time = time.time()

        try:
            logger.info(
                "Starting background profile refresh",
                extra={"user_id": user_id}
            )

            # Call get_user_profile MCP tool
            async with MCPClient() as mcp_client:
                result = await mcp_client.call_tool(
                    "get_user_profile",
                    {"user_id": user_id}
                )

            duration_ms = int((time.time() - start_time) * 1000)

            # Check if tool call succeeded
            if result.get("status") == "success":
                # Build profile object for caching (all 8 categories)
                profile = {
                    "user_id": user_id,
                    "completeness": result.get("completeness", 0),
                    "basics": result.get("basics", {}),
                    "preferences": result.get("preferences", {}),
                    "goals": result.get("goals", {}),
                    "interests": result.get("interests", {}),
                    "background": result.get("background", {}),
                    "health": result.get("health", {}),
                    "personality": result.get("personality", {}),
                    "values": result.get("values", {})
                }

                # Store in Redis with TTL
                cache_key = f"profile:{user_id}"
                await self.redis_client.setex(
                    cache_key,
                    self.PROFILE_CACHE_TTL,
                    json.dumps(profile)
                )

                # Update metadata (last_refresh timestamp)
                await self._update_last_refresh(user_id)

                logger.info(
                    "Profile refreshed successfully",
                    extra={
                        "user_id": user_id,
                        "completeness": profile["completeness"],
                        "duration_ms": duration_ms,
                        "ttl": self.PROFILE_CACHE_TTL
                    }
                )

            else:
                # Tool call failed - log error but don't crash
                error_msg = result.get("error", "Unknown error")
                logger.warning(
                    f"Profile refresh failed - MCP tool error: {error_msg}",
                    extra={
                        "user_id": user_id,
                        "duration_ms": duration_ms,
                        "error": error_msg
                    }
                )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                f"Background profile refresh failed: {str(e)}",
                extra={
                    "user_id": user_id,
                    "duration_ms": duration_ms,
                    "error_type": type(e).__name__
                },
                exc_info=True
            )
            # Don't raise - this is a background task, failures should not block

    @observe(name="profile_fetch_fresh", as_type="span")
    async def fetch_profile_fresh(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch fresh profile from agentic-memories and return it.

        Unlike refresh_profile_background() which only updates cache,
        this method fetches fresh profile, updates cache, AND returns the profile.
        Designed for proactive agent context where fresh data is critical.

        Falls back to cached profile if MCP call fails.

        Args:
            user_id: User identifier

        Returns:
            Profile dict if successful, cached profile if MCP fails, None if both fail
        """
        start_time = time.time()

        try:
            logger.info(
                "Fetching fresh profile via MCP",
                extra={"user_id": user_id}
            )

            # Call get_user_profile MCP tool
            async with MCPClient() as mcp_client:
                result = await mcp_client.call_tool(
                    "get_user_profile",
                    {"user_id": user_id}
                )

            duration_ms = int((time.time() - start_time) * 1000)

            # Check if tool call succeeded
            if result.get("status") == "success":
                # Build profile object
                profile = {
                    "user_id": user_id,
                    "completeness_pct": result.get("completeness_pct", 0),
                    "basics": result.get("basics", {}),
                    "preferences": result.get("preferences", {}),
                    "goals": result.get("goals", {}),
                    "interests": result.get("interests", {}),
                    "background": result.get("background", {})
                }

                # Update cache with fresh data
                cache_key = f"profile:{user_id}"
                await self.redis_client.setex(
                    cache_key,
                    self.PROFILE_CACHE_TTL,
                    json.dumps(profile)
                )

                # Update metadata (last_refresh timestamp)
                await self._update_last_refresh(user_id)

                logger.info(
                    "Fresh profile fetched successfully",
                    extra={
                        "user_id": user_id,
                        "completeness_pct": profile["completeness_pct"],
                        "duration_ms": duration_ms
                    }
                )

                return profile

            else:
                # Tool call failed - fall back to cache
                error_msg = result.get("error", "Unknown error")
                logger.warning(
                    f"Fresh profile fetch failed - falling back to cache: {error_msg}",
                    extra={
                        "user_id": user_id,
                        "duration_ms": duration_ms,
                        "error": error_msg
                    }
                )
                return await self.load_profile_from_cache(user_id)

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning(
                f"Fresh profile fetch failed - falling back to cache: {str(e)}",
                extra={
                    "user_id": user_id,
                    "duration_ms": duration_ms,
                    "error_type": type(e).__name__
                }
            )
            # Fall back to cached profile
            try:
                return await self.load_profile_from_cache(user_id)
            except Exception:
                return None

    async def check_refresh_triggers(self, user_id: str, message_count: Optional[int] = None) -> bool:
        """
        Check if profile refresh should be triggered.

        Triggers:
        - Message count mod 5 == 0 (every 5 messages)
        - Time since last_refresh > 15 minutes

        Args:
            user_id: User identifier
            message_count: Current message count (if already known, to avoid race condition)

        Returns:
            bool: True if refresh should be triggered, False otherwise
        """
        try:
            meta_key = f"profile_meta:{user_id}"

            # If message_count not provided, read from Redis Hash
            if message_count is None:
                # Read all fields from hash
                metadata = await self.redis_client.hgetall(meta_key)

                if not metadata:
                    # First time - should trigger refresh
                    logger.info(
                        "Profile metadata not found - triggering first refresh",
                        extra={"user_id": user_id}
                    )
                    return True

                # Parse message_count (Redis returns strings)
                message_count = int(metadata.get("message_count", "0") or "0")
                last_refresh_str = metadata.get("last_refresh")
            else:
                # Message count provided - read only last_refresh for time-based trigger
                last_refresh_str = await self.redis_client.hget(meta_key, "last_refresh")

                if last_refresh_str is None:
                    # Check if hash exists at all
                    exists = await self.redis_client.exists(meta_key)
                    if not exists:
                        # First time - should trigger refresh
                        logger.info(
                            "Profile metadata not found - triggering first refresh",
                            extra={"user_id": user_id}
                        )
                        return True

            # Check message count trigger
            if message_count > 0 and message_count % self.MESSAGE_COUNT_TRIGGER == 0:
                logger.info(
                    "Message count trigger activated",
                    extra={
                        "user_id": user_id,
                        "message_count": message_count,
                        "trigger": "message_count"
                    }
                )
                return True

            # Check time-based trigger
            if last_refresh_str:
                last_refresh = datetime.fromisoformat(last_refresh_str)
                time_since_refresh = datetime.now(timezone.utc) - last_refresh
                minutes_since_refresh = time_since_refresh.total_seconds() / 60

                if minutes_since_refresh >= self.TIME_TRIGGER_MINUTES:
                    logger.info(
                        "Time trigger activated",
                        extra={
                            "user_id": user_id,
                            "minutes_since_refresh": int(minutes_since_refresh),
                            "trigger": "time_based"
                        }
                    )
                    return True

            return False

        except Exception as e:
            logger.error(
                f"Error checking refresh triggers: {str(e)}",
                extra={
                    "user_id": user_id,
                    "error_type": type(e).__name__
                }
            )
            # On error, don't trigger refresh to avoid spam
            return False

    async def increment_message_count(self, user_id: str) -> int:
        """
        Increment message count for user.

        Used to track message-based refresh triggers.
        Uses Redis HINCRBY for atomic increment to avoid race conditions.

        Args:
            user_id: User identifier

        Returns:
            int: New message count
        """
        try:
            meta_key = f"profile_meta:{user_id}"

            # Use HINCRBY for atomic increment (avoids read-modify-write race)
            message_count = await self.redis_client.hincrby(meta_key, "message_count", 1)

            # Reset TTL after increment to keep metadata fresh
            await self.redis_client.expire(meta_key, self.PROFILE_META_TTL)

            logger.debug(
                "Message count incremented atomically",
                extra={
                    "user_id": user_id,
                    "message_count": message_count
                }
            )

            return message_count

        except Exception as e:
            logger.error(
                f"Error incrementing message count: {str(e)}",
                extra={
                    "user_id": user_id,
                    "error_type": type(e).__name__
                }
            )
            return 0

    async def _update_last_refresh(self, user_id: str) -> None:
        """
        Update last_refresh timestamp in metadata.

        Internal method called after successful profile refresh.
        Uses Redis HSET for atomic field update to avoid race conditions.

        Args:
            user_id: User identifier
        """
        try:
            meta_key = f"profile_meta:{user_id}"
            last_refresh = datetime.now(timezone.utc).isoformat()

            # Use HSET for atomic field update (avoids read-modify-write race)
            await self.redis_client.hset(meta_key, "last_refresh", last_refresh)

            # Reset TTL after update to keep metadata fresh
            await self.redis_client.expire(meta_key, self.PROFILE_META_TTL)

            logger.debug(
                "Updated last_refresh timestamp atomically",
                extra={
                    "user_id": user_id,
                    "last_refresh": last_refresh
                }
            )

        except Exception as e:
            logger.error(
                f"Error updating last_refresh: {str(e)}",
                extra={
                    "user_id": user_id,
                    "error_type": type(e).__name__
                }
            )
