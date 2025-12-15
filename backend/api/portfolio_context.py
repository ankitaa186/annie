"""
Portfolio Context Management Module

Redis-based portfolio caching for LLM context injection.
Integrates with agentic-memories portfolio API via MCP tools.

Redis Key Pattern:
- portfolio:{user_id} -> Portfolio data (JSON, TTL: 300s = 5 min)

Follows the same pattern as profile.py but simplified for portfolio data.
"""

import json
import time
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


class PortfolioManager:
    """
    Async Redis-based portfolio manager with caching.

    Features:
    - Non-blocking cache-first portfolio loading (<10ms)
    - 5-minute TTL (shorter than profile due to more dynamic nature)
    - Graceful degradation (returns empty portfolio if service unavailable)

    Redis Keys:
    - portfolio:{user_id} - Cached portfolio data (TTL: 300s)
    """

    # Cache TTL: 5 minutes (300 seconds) - shorter than profile (15 min)
    PORTFOLIO_CACHE_TTL = 300

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """
        Initialize PortfolioManager.

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

    @observe(name="portfolio_cache_load", as_type="span")
    async def load_portfolio_from_cache(self, user_id: str) -> Dict[str, Any]:
        """
        Load user portfolio from Redis cache (non-blocking, <10ms).

        Returns cached portfolio if available, empty portfolio if not cached.
        Never blocks - always returns immediately.

        Args:
            user_id: User identifier

        Returns:
            dict: Portfolio object with holdings, or empty portfolio if not cached

        Example return (cached):
            {
                "user_id": "123456",
                "holdings": [
                    {"ticker": "AAPL", "shares": 10, "avg_price": 175.50, ...},
                    {"ticker": "GOOGL", "shares": 5, "avg_price": 145.00, ...}
                ],
                "total_holdings": 2,
                "cached": true
            }

        Example return (empty):
            {
                "user_id": "123456",
                "holdings": [],
                "total_holdings": 0,
                "cached": false
            }
        """
        start_time = time.time()

        try:
            cache_key = f"portfolio:{user_id}"
            cached_data = await self.redis_client.get(cache_key)

            duration_ms = int((time.time() - start_time) * 1000)

            if cached_data:
                portfolio = json.loads(cached_data)
                portfolio["cached"] = True

                logger.info(
                    "Portfolio loaded from cache",
                    extra={
                        "user_id": user_id,
                        "holdings_count": portfolio.get("total_holdings", 0),
                        "duration_ms": duration_ms,
                        "cache_hit": True
                    }
                )

                return portfolio
            else:
                # Return empty portfolio - will be populated on next refresh
                empty_portfolio = {
                    "user_id": user_id,
                    "holdings": [],
                    "total_holdings": 0,
                    "cached": False
                }

                logger.info(
                    "Portfolio cache miss - returning empty portfolio",
                    extra={
                        "user_id": user_id,
                        "duration_ms": duration_ms,
                        "cache_hit": False
                    }
                )

                return empty_portfolio

        except redis.RedisError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                f"Redis error loading portfolio cache: {str(e)}",
                extra={
                    "user_id": user_id,
                    "duration_ms": duration_ms,
                    "error_type": type(e).__name__
                }
            )
            # Return empty portfolio - graceful degradation
            return {
                "user_id": user_id,
                "holdings": [],
                "total_holdings": 0,
                "cached": False
            }

    @observe(name="portfolio_refresh", as_type="span")
    async def refresh_portfolio(self, user_id: str) -> Dict[str, Any]:
        """
        Refresh portfolio from agentic-memories and update Redis cache.

        Calls get_portfolio MCP tool, updates cache with TTL=300s.

        Args:
            user_id: User identifier

        Returns:
            dict: Fresh portfolio data
        """
        start_time = time.time()

        try:
            logger.info(
                "Refreshing portfolio from agentic-memories",
                extra={"user_id": user_id}
            )

            # Call get_portfolio MCP tool
            async with MCPClient() as mcp_client:
                result = await mcp_client.call_tool(
                    "get_portfolio",
                    {"user_id": user_id}
                )

            duration_ms = int((time.time() - start_time) * 1000)

            # Check if tool call succeeded
            if result.get("status") == "success":
                # Build portfolio object for caching
                portfolio = {
                    "user_id": user_id,
                    "holdings": result.get("holdings", []),
                    "total_holdings": result.get("total_holdings", 0),
                    "last_updated": result.get("last_updated")
                }

                # Store in Redis with TTL
                cache_key = f"portfolio:{user_id}"
                await self.redis_client.setex(
                    cache_key,
                    self.PORTFOLIO_CACHE_TTL,
                    json.dumps(portfolio)
                )

                logger.info(
                    "Portfolio refreshed successfully",
                    extra={
                        "user_id": user_id,
                        "holdings_count": portfolio["total_holdings"],
                        "duration_ms": duration_ms,
                        "ttl": self.PORTFOLIO_CACHE_TTL
                    }
                )

                portfolio["cached"] = True
                return portfolio

            else:
                # Tool call failed - log error and return empty
                error_msg = result.get("message", "Unknown error")
                logger.warning(
                    f"Portfolio refresh failed - MCP tool error: {error_msg}",
                    extra={
                        "user_id": user_id,
                        "duration_ms": duration_ms,
                        "error": error_msg
                    }
                )

                return {
                    "user_id": user_id,
                    "holdings": [],
                    "total_holdings": 0,
                    "cached": False
                }

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                f"Portfolio refresh failed: {str(e)}",
                extra={
                    "user_id": user_id,
                    "duration_ms": duration_ms,
                    "error_type": type(e).__name__
                },
                exc_info=True
            )
            # Return empty portfolio on error
            return {
                "user_id": user_id,
                "holdings": [],
                "total_holdings": 0,
                "cached": False
            }

    async def get_portfolio(self, user_id: str, refresh_if_empty: bool = True) -> Dict[str, Any]:
        """
        Get portfolio, refreshing if cache is empty.

        Convenience method that loads from cache and optionally refreshes if empty.

        Args:
            user_id: User identifier
            refresh_if_empty: If True, refresh from agentic-memories when cache is empty

        Returns:
            dict: Portfolio data (from cache or fresh)
        """
        # Try loading from cache first
        portfolio = await self.load_portfolio_from_cache(user_id)

        # If cache miss and refresh enabled, fetch fresh data
        if not portfolio.get("cached") and refresh_if_empty and portfolio.get("total_holdings", 0) == 0:
            portfolio = await self.refresh_portfolio(user_id)

        return portfolio

    async def invalidate_cache(self, user_id: str) -> bool:
        """
        Invalidate cached portfolio for user.

        Call this when portfolio is modified (e.g., after add_holding).

        Args:
            user_id: User identifier

        Returns:
            bool: True if cache was invalidated, False on error
        """
        try:
            cache_key = f"portfolio:{user_id}"
            await self.redis_client.delete(cache_key)

            logger.info(
                "Portfolio cache invalidated",
                extra={"user_id": user_id}
            )
            return True

        except Exception as e:
            logger.error(
                f"Error invalidating portfolio cache: {str(e)}",
                extra={
                    "user_id": user_id,
                    "error_type": type(e).__name__
                }
            )
            return False
