"""
Rate Limiter Middleware

Implements per-user rate limiting using Redis sliding window.
Returns 429 Too Many Requests with Retry-After header when limit exceeded.

Configuration:
- Default: 60 requests per minute per user
- Rate limit only applies to authenticated users
- Unauthenticated requests bypass rate limiting (rely on CF rate limits)
"""

import time
from datetime import datetime, timezone
from typing import Optional, Tuple

import redis.asyncio as redis
from fastapi import Request
from fastapi.responses import JSONResponse

from api.config import get_config
from api.logging import get_logger

logger = get_logger(__name__)

# Rate limit configuration
RATE_LIMIT_REQUESTS = 60  # requests per window
RATE_LIMIT_WINDOW = 60     # window in seconds (1 minute)
RATE_LIMIT_KEY_PREFIX = "ratelimit"


class RateLimiter:
    """
    Redis-based sliding window rate limiter.

    Uses sorted sets to track request timestamps per user.
    Allows efficient sliding window calculations.
    """

    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        requests: int = RATE_LIMIT_REQUESTS,
        window: int = RATE_LIMIT_WINDOW
    ):
        """
        Initialize rate limiter.

        Args:
            redis_client: Optional Redis client (creates new if not provided)
            requests: Max requests per window
            window: Window size in seconds
        """
        self.requests = requests
        self.window = window

        if redis_client:
            self.redis_client = redis_client
            self._should_close = False
        else:
            try:
                config = get_config()
                redis_host = config.get("REDIS_HOST", "redis")
                redis_port = int(config.get("REDIS_PORT", 6379))
            except Exception:
                redis_host = "redis"
                redis_port = 6379

            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=0,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2
            )
            self._should_close = True

    async def close(self):
        """Close Redis connection if owned."""
        if self._should_close and self.redis_client:
            await self.redis_client.close()

    async def is_rate_limited(self, user_id: str) -> Tuple[bool, int, int]:
        """
        Check if user is rate limited.

        Uses sliding window algorithm:
        1. Get current timestamp
        2. Remove entries older than window
        3. Count remaining entries
        4. If count >= limit, rate limited
        5. Otherwise, add current timestamp

        Args:
            user_id: User identifier for rate limiting

        Returns:
            Tuple of (is_limited, remaining_requests, retry_after_seconds)
        """
        key = f"{RATE_LIMIT_KEY_PREFIX}:{user_id}"
        now = time.time()
        window_start = now - self.window

        try:
            pipe = self.redis_client.pipeline()

            # Remove old entries outside the window
            pipe.zremrangebyscore(key, 0, window_start)

            # Count current requests in window
            pipe.zcard(key)

            # Execute pipeline
            results = await pipe.execute()
            current_count = results[1]

            if current_count >= self.requests:
                # Rate limited - calculate retry after
                # Get oldest entry to calculate when it expires
                oldest = await self.redis_client.zrange(key, 0, 0, withscores=True)
                if oldest:
                    oldest_time = oldest[0][1]
                    retry_after = int(oldest_time + self.window - now) + 1
                else:
                    retry_after = self.window

                logger.warning(
                    "Rate limit exceeded",
                    extra={
                        "user_id": user_id,
                        "current_count": current_count,
                        "limit": self.requests,
                        "retry_after": retry_after,
                        "event": "rate_limit_exceeded"
                    }
                )

                return True, 0, max(retry_after, 1)

            # Not rate limited - add this request
            await self.redis_client.zadd(key, {str(now): now})
            await self.redis_client.expire(key, self.window * 2)  # Extra buffer for cleanup

            remaining = self.requests - current_count - 1

            logger.debug(
                "Rate limit check passed",
                extra={
                    "user_id": user_id,
                    "remaining": remaining,
                    "limit": self.requests
                }
            )

            return False, remaining, 0

        except Exception as e:
            # On Redis failure, allow request (fail open for availability)
            logger.error(
                "Rate limiter Redis error, allowing request",
                extra={
                    "user_id": user_id,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            return False, self.requests, 0


async def rate_limit_middleware(request: Request, call_next):
    """
    Rate limiting middleware for FastAPI.

    Only applies to authenticated users (with user_id in request.state).
    Unauthenticated requests pass through (rely on upstream rate limits).

    Args:
        request: FastAPI Request object
        call_next: Next middleware/handler in chain

    Returns:
        Response from next handler or 429 JSONResponse
    """
    # Skip rate limiting for health checks and static paths
    path = request.url.path
    if path in ("/health", "/health/full", "/", "/docs", "/openapi.json", "/redoc"):
        return await call_next(request)

    # Check if user is authenticated
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        # No auth - skip rate limiting (rely on CF rate limits)
        return await call_next(request)

    # Apply rate limiting
    rate_limiter = RateLimiter()
    try:
        is_limited, remaining, retry_after = await rate_limiter.is_rate_limited(user_id)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": "Too many requests. Please slow down.",
                        "retry_after": retry_after,
                        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                    }
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(RATE_LIMIT_REQUESTS),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after)
                }
            )

        # Process request and add rate limit headers to response
        response = await call_next(request)

        # Add rate limit headers to response
        response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT_REQUESTS)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + RATE_LIMIT_WINDOW)

        return response

    finally:
        await rate_limiter.close()
