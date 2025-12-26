"""
Condition Evaluators for Proactive AI Triggers

Fast, LLM-free condition evaluators for different trigger types:
- PriceEvaluator: Stock price conditions (e.g., "NVDA < 130")
- PortfolioEvaluator: Portfolio conditions (e.g., "any_holding_change > 5%")
- SilenceEvaluator: User inactivity detection (e.g., "silence > 4h")

All evaluators follow fail-safe behavior: return False on error to prevent false alarms.
"""

import asyncio
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import redis.asyncio as redis
import yfinance as yf

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


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class EvaluatorResult:
    """
    Result of a condition evaluation.

    Attributes:
        met: Whether the condition is met (True) or not (False)
        reason: Human-readable explanation of the result
        data: Additional context data for trigger_data field (current values, etc.)
    """
    met: bool
    reason: str
    data: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Base Evaluator
# ============================================================================

class Evaluator(ABC):
    """Abstract base class for all condition evaluators."""

    def __init__(self):
        """Initialize evaluator with Redis connection."""
        self.config = get_config()
        self.redis_client: Optional[redis.Redis] = None
        self._owned_redis = False

    async def _get_redis_client(self) -> redis.Redis:
        """Get or create Redis client connection."""
        if self.redis_client is None:
            redis_host = self.config.get("REDIS_HOST", "redis")
            redis_port = int(self.config.get("REDIS_PORT", 6379))
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                decode_responses=True
            )
            self._owned_redis = True
            logger.debug(f"Created Redis connection to {redis_host}:{redis_port}")
        return self.redis_client

    async def close(self):
        """Close Redis connection if owned by this evaluator."""
        if self._owned_redis and self.redis_client:
            await self.redis_client.close()
            logger.debug("Closed Redis connection")

    @abstractmethod
    async def evaluate(self, expression: str, user_id: str) -> EvaluatorResult:
        """
        Evaluate a condition expression.

        Args:
            expression: Condition expression to evaluate
            user_id: User identifier for context

        Returns:
            EvaluatorResult with met status and details
        """
        pass


# ============================================================================
# Price Evaluator
# ============================================================================

class PriceEvaluator(Evaluator):
    """
    Evaluates stock price conditions using yfinance.

    Expression format: "TICKER OPERATOR VALUE"
    Examples: "NVDA < 130", "AAPL >= 180", "TSLA > 250"

    Features:
    - 60-second price caching (avoid yfinance rate limits)
    - Retry with exponential backoff (yfinance is unreliable)
    - Fail-safe: returns False on any error
    """

    # Price cache configuration
    PRICE_CACHE_TTL = 60  # seconds - shorter than portfolio cache for responsiveness
    CACHE_KEY_PREFIX = "price_cache:"

    # Retry configuration for yfinance (unofficial scraper, can fail)
    MAX_RETRIES = 3
    RETRY_DELAYS = [1, 2, 4]  # exponential backoff in seconds

    # Expression parsing regex: "TICKER OPERATOR VALUE"
    EXPRESSION_PATTERN = re.compile(r'([A-Z0-9\.]+)\s*([<>]=?)\s*([\d.]+)')

    # Ticker validation pattern
    TICKER_PATTERN = re.compile(r'^[A-Z0-9\.]{1,10}$')

    @observe(name="price_evaluator", as_type="span")
    async def evaluate(self, expression: str, user_id: str) -> EvaluatorResult:
        """
        Evaluate price condition.

        Args:
            expression: Price expression (e.g., "NVDA < 130")
            user_id: User identifier for logging

        Returns:
            EvaluatorResult with met status and price data
        """
        start_time = time.time()

        try:
            # Parse expression
            ticker, operator, threshold = self._parse_expression(expression)

            # Fetch current price (with caching and retry)
            current_price = await self._fetch_price_with_retry(ticker)

            if current_price is None:
                # Failed to fetch price after retries - fail-safe
                logger.warning(
                    "Price fetch failed - failing safe (returning False)",
                    extra={
                        "ticker": ticker,
                        "expression": expression,
                        "user_id": user_id,
                        "duration_ms": round((time.time() - start_time) * 1000, 2)
                    }
                )
                return EvaluatorResult(
                    met=False,
                    reason=f"Failed to fetch price for {ticker}",
                    data={"ticker": ticker, "threshold": threshold, "operator": operator}
                )

            # Evaluate condition
            met = self._evaluate_operator(current_price, operator, threshold)

            duration_ms = round((time.time() - start_time) * 1000, 2)

            logger.info(
                "Price condition evaluated",
                extra={
                    "ticker": ticker,
                    "current_price": current_price,
                    "operator": operator,
                    "threshold": threshold,
                    "met": met,
                    "expression": expression,
                    "user_id": user_id,
                    "duration_ms": duration_ms
                }
            )

            return EvaluatorResult(
                met=met,
                reason=f"{ticker} is ${current_price:.2f} (threshold: {operator} ${threshold:.2f})",
                data={
                    "ticker": ticker,
                    "current_price": current_price,
                    "threshold": threshold,
                    "operator": operator
                }
            )

        except ValueError as e:
            # Expression parsing error - fail-safe
            logger.error(
                "Failed to parse price expression - failing safe",
                extra={
                    "expression": expression,
                    "error": str(e),
                    "user_id": user_id,
                    "duration_ms": round((time.time() - start_time) * 1000, 2)
                }
            )
            return EvaluatorResult(
                met=False,
                reason=f"Invalid expression: {str(e)}",
                data={"expression": expression}
            )

        except Exception as e:
            # Unexpected error - fail-safe
            logger.error(
                "Unexpected error in price evaluator - failing safe",
                extra={
                    "expression": expression,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "user_id": user_id,
                    "duration_ms": round((time.time() - start_time) * 1000, 2)
                }
            )
            return EvaluatorResult(
                met=False,
                reason=f"Error evaluating price condition: {str(e)}",
                data={"expression": expression}
            )

    def _parse_expression(self, expression: str) -> tuple[str, str, float]:
        """
        Parse price expression into components.

        Args:
            expression: Price expression (e.g., "NVDA < 130")

        Returns:
            tuple: (ticker, operator, threshold)

        Raises:
            ValueError: If expression is invalid
        """
        match = self.EXPRESSION_PATTERN.match(expression.strip())
        if not match:
            raise ValueError(
                f"Invalid price expression format. Expected 'TICKER OPERATOR VALUE' "
                f"(e.g., 'NVDA < 130'), got: {expression}"
            )

        ticker_raw, operator, value_str = match.groups()

        # Normalize ticker
        ticker = self._normalize_ticker(ticker_raw)
        if ticker is None:
            raise ValueError(f"Invalid ticker format: {ticker_raw}")

        # Parse threshold value
        try:
            threshold = float(value_str)
        except ValueError:
            raise ValueError(f"Invalid threshold value: {value_str}")

        # Validate operator
        if operator not in ['<', '>', '<=', '>=']:
            raise ValueError(f"Invalid operator: {operator}")

        return ticker, operator, threshold

    def _normalize_ticker(self, ticker: str) -> Optional[str]:
        """
        Normalize and validate ticker symbol.

        Args:
            ticker: Raw ticker symbol

        Returns:
            Normalized uppercase ticker or None if invalid
        """
        if not ticker:
            return None

        normalized = ticker.upper().strip()

        if not self.TICKER_PATTERN.match(normalized):
            logger.warning(f"Invalid ticker format rejected: {ticker}")
            return None

        return normalized

    def _evaluate_operator(self, current: float, operator: str, threshold: float) -> bool:
        """Evaluate comparison operator."""
        if operator == '<':
            return current < threshold
        elif operator == '>':
            return current > threshold
        elif operator == '<=':
            return current <= threshold
        elif operator == '>=':
            return current >= threshold
        return False

    async def _fetch_price_with_retry(self, ticker: str) -> Optional[float]:
        """
        Fetch price with caching and retry logic.

        Args:
            ticker: Stock ticker symbol (normalized)

        Returns:
            Current price or None if failed after all retries
        """
        # Check cache first
        cached_price = await self._get_cached_price(ticker)
        if cached_price is not None:
            logger.debug(f"Price cache hit for {ticker}: ${cached_price:.2f}")
            return cached_price

        # Cache miss - fetch from yfinance with retry
        for attempt in range(self.MAX_RETRIES):
            try:
                logger.debug(
                    f"Fetching price from yfinance (attempt {attempt + 1}/{self.MAX_RETRIES})",
                    extra={"ticker": ticker, "attempt": attempt + 1}
                )

                # Fetch price from yfinance
                ticker_obj = yf.Ticker(ticker)
                info = ticker_obj.info

                # Try multiple price fields (yfinance can be inconsistent)
                price = info.get('currentPrice') or info.get('regularMarketPrice')

                if price is None:
                    # Try fast_info as fallback
                    try:
                        price = ticker_obj.fast_info.get('lastPrice')
                    except Exception:
                        pass

                if price is not None:
                    # Success - cache and return
                    await self._cache_price(ticker, price)
                    logger.info(
                        f"Fetched price from yfinance: {ticker} = ${price:.2f}",
                        extra={"ticker": ticker, "price": price, "attempt": attempt + 1}
                    )
                    return float(price)
                else:
                    logger.warning(
                        f"yfinance returned no price for {ticker}",
                        extra={"ticker": ticker, "attempt": attempt + 1}
                    )

            except Exception as e:
                logger.warning(
                    f"yfinance fetch failed for {ticker}: {str(e)}",
                    extra={
                        "ticker": ticker,
                        "attempt": attempt + 1,
                        "error": str(e),
                        "error_type": type(e).__name__
                    }
                )

            # Wait before retry (exponential backoff)
            if attempt < self.MAX_RETRIES - 1:
                delay = self.RETRY_DELAYS[attempt]
                logger.debug(f"Retrying after {delay}s delay...")
                await asyncio.sleep(delay)

        # All retries failed
        logger.error(
            f"Failed to fetch price for {ticker} after {self.MAX_RETRIES} attempts",
            extra={"ticker": ticker, "max_retries": self.MAX_RETRIES}
        )
        return None

    async def _get_cached_price(self, ticker: str) -> Optional[float]:
        """
        Get cached price from Redis.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Cached price or None if not cached
        """
        try:
            redis_client = await self._get_redis_client()
            cache_key = f"{self.CACHE_KEY_PREFIX}{ticker}"
            cached_value = await redis_client.get(cache_key)

            if cached_value:
                return float(cached_value)

        except Exception as e:
            logger.warning(f"Redis cache read failed for {ticker}: {e}")

        return None

    async def _cache_price(self, ticker: str, price: float) -> None:
        """
        Cache price in Redis.

        Args:
            ticker: Stock ticker symbol
            price: Current price
        """
        try:
            redis_client = await self._get_redis_client()
            cache_key = f"{self.CACHE_KEY_PREFIX}{ticker}"
            await redis_client.set(
                cache_key,
                str(price),
                ex=self.PRICE_CACHE_TTL
            )
            logger.debug(
                f"Cached price for {ticker}: ${price:.2f} (TTL: {self.PRICE_CACHE_TTL}s)"
            )
        except Exception as e:
            logger.warning(f"Redis cache write failed for {ticker}: {e}")


# ============================================================================
# Portfolio Evaluator
# ============================================================================

class PortfolioEvaluator(Evaluator):
    """
    Evaluates portfolio conditions using get_portfolio MCP tool.

    Expression formats:
    - "any_holding_change > X%" - Any holding changed by more than X%
    - "any_holding_down > X%" - Any holding down by more than X%
    - "total_value >= X" - Total portfolio value at least X
    - "total_change > X%" - Total portfolio changed by more than X%

    Features:
    - Uses MCP client to fetch portfolio data
    - Supports multiple expression types
    - Fail-safe: returns False on any error
    """

    # Expression parsing regex
    EXPRESSION_PATTERN = re.compile(
        r'(any_holding_change|any_holding_down|total_value|total_change)\s*([<>]=?)\s*([\d.]+)%?'
    )

    @observe(name="portfolio_evaluator", as_type="span")
    async def evaluate(self, expression: str, user_id: str) -> EvaluatorResult:
        """
        Evaluate portfolio condition.

        Args:
            expression: Portfolio expression (e.g., "any_holding_change > 5%")
            user_id: User identifier

        Returns:
            EvaluatorResult with met status and portfolio data
        """
        start_time = time.time()

        try:
            # Parse expression
            condition_type, operator, threshold = self._parse_expression(expression)

            # Fetch portfolio
            portfolio = await self._fetch_portfolio(user_id)

            if portfolio is None:
                # Failed to fetch portfolio - fail-safe
                logger.warning(
                    "Portfolio fetch failed - failing safe (returning False)",
                    extra={
                        "expression": expression,
                        "user_id": user_id,
                        "duration_ms": round((time.time() - start_time) * 1000, 2)
                    }
                )
                return EvaluatorResult(
                    met=False,
                    reason="Failed to fetch portfolio",
                    data={"condition_type": condition_type, "threshold": threshold}
                )

            # Evaluate condition based on type
            if condition_type == "any_holding_change":
                met, details = self._check_any_holding_change(portfolio, operator, threshold)
            elif condition_type == "any_holding_down":
                met, details = self._check_any_holding_down(portfolio, operator, threshold)
            elif condition_type == "total_value":
                met, details = self._check_total_value(portfolio, operator, threshold)
            elif condition_type == "total_change":
                met, details = self._check_total_change(portfolio, operator, threshold)
            else:
                raise ValueError(f"Unknown condition type: {condition_type}")

            duration_ms = round((time.time() - start_time) * 1000, 2)

            logger.info(
                "Portfolio condition evaluated",
                extra={
                    "condition_type": condition_type,
                    "operator": operator,
                    "threshold": threshold,
                    "met": met,
                    "details": details,
                    "expression": expression,
                    "user_id": user_id,
                    "duration_ms": duration_ms
                }
            )

            return EvaluatorResult(
                met=met,
                reason=details.get("reason", "Portfolio condition evaluated"),
                data=details
            )

        except ValueError as e:
            # Expression parsing error - fail-safe
            logger.error(
                "Failed to parse portfolio expression - failing safe",
                extra={
                    "expression": expression,
                    "error": str(e),
                    "user_id": user_id,
                    "duration_ms": round((time.time() - start_time) * 1000, 2)
                }
            )
            return EvaluatorResult(
                met=False,
                reason=f"Invalid expression: {str(e)}",
                data={"expression": expression}
            )

        except Exception as e:
            # Unexpected error - fail-safe
            logger.error(
                "Unexpected error in portfolio evaluator - failing safe",
                extra={
                    "expression": expression,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "user_id": user_id,
                    "duration_ms": round((time.time() - start_time) * 1000, 2)
                }
            )
            return EvaluatorResult(
                met=False,
                reason=f"Error evaluating portfolio condition: {str(e)}",
                data={"expression": expression}
            )

    def _parse_expression(self, expression: str) -> tuple[str, str, float]:
        """
        Parse portfolio expression into components.

        Args:
            expression: Portfolio expression

        Returns:
            tuple: (condition_type, operator, threshold)

        Raises:
            ValueError: If expression is invalid
        """
        match = self.EXPRESSION_PATTERN.match(expression.strip())
        if not match:
            raise ValueError(
                f"Invalid portfolio expression format. Expected "
                f"'any_holding_change/any_holding_down/total_value/total_change OPERATOR VALUE', "
                f"got: {expression}"
            )

        condition_type, operator, value_str = match.groups()

        # Parse threshold value
        try:
            threshold = float(value_str)
        except ValueError:
            raise ValueError(f"Invalid threshold value: {value_str}")

        # Validate operator
        if operator not in ['<', '>', '<=', '>=']:
            raise ValueError(f"Invalid operator: {operator}")

        return condition_type, operator, threshold

    async def _fetch_portfolio(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch portfolio via MCP get_portfolio tool.

        Args:
            user_id: User identifier

        Returns:
            Portfolio dict or None if failed
        """
        try:
            async with MCPClient() as mcp_client:
                result = await mcp_client.call_tool(
                    "get_portfolio",
                    {"user_id": user_id}
                )

                if result.get("status") == "success":
                    return result.get("portfolio", {})
                else:
                    logger.warning(
                        f"MCP get_portfolio returned error: {result.get('message')}",
                        extra={"user_id": user_id, "result": result}
                    )
                    return None

        except Exception as e:
            logger.error(
                f"Failed to fetch portfolio via MCP: {str(e)}",
                extra={"user_id": user_id, "error": str(e)}
            )
            return None

    def _check_any_holding_change(
        self,
        portfolio: Dict[str, Any],
        operator: str,
        threshold: float
    ) -> tuple[bool, Dict[str, Any]]:
        """
        Check if any holding changed by more than threshold.

        Returns:
            tuple: (met, details_dict)
        """
        holdings = portfolio.get("holdings", [])

        if not holdings:
            return False, {
                "reason": "No holdings in portfolio",
                "condition_type": "any_holding_change",
                "threshold": threshold
            }

        max_change = 0.0
        max_change_ticker = None

        for holding in holdings:
            change_pct = abs(holding.get("change_pct", 0.0))
            if change_pct > max_change:
                max_change = change_pct
                max_change_ticker = holding.get("ticker", "UNKNOWN")

        met = self._evaluate_operator(max_change, operator, threshold)

        return met, {
            "reason": f"Max holding change: {max_change:.2f}% ({max_change_ticker})",
            "condition_type": "any_holding_change",
            "max_change": max_change,
            "max_change_ticker": max_change_ticker,
            "threshold": threshold,
            "operator": operator
        }

    def _check_any_holding_down(
        self,
        portfolio: Dict[str, Any],
        operator: str,
        threshold: float
    ) -> tuple[bool, Dict[str, Any]]:
        """
        Check if any holding is down by more than threshold.

        Returns:
            tuple: (met, details_dict)
        """
        holdings = portfolio.get("holdings", [])

        if not holdings:
            return False, {
                "reason": "No holdings in portfolio",
                "condition_type": "any_holding_down",
                "threshold": threshold
            }

        max_down = 0.0
        max_down_ticker = None

        for holding in holdings:
            change_pct = holding.get("change_pct", 0.0)
            if change_pct < 0:  # Only negative changes
                down_amount = abs(change_pct)
                if down_amount > max_down:
                    max_down = down_amount
                    max_down_ticker = holding.get("ticker", "UNKNOWN")

        met = self._evaluate_operator(max_down, operator, threshold)

        return met, {
            "reason": f"Max holding down: {max_down:.2f}% ({max_down_ticker or 'none'})",
            "condition_type": "any_holding_down",
            "max_down": max_down,
            "max_down_ticker": max_down_ticker,
            "threshold": threshold,
            "operator": operator
        }

    def _check_total_value(
        self,
        portfolio: Dict[str, Any],
        operator: str,
        threshold: float
    ) -> tuple[bool, Dict[str, Any]]:
        """
        Check if total portfolio value meets threshold.

        Returns:
            tuple: (met, details_dict)
        """
        total_value = portfolio.get("total_value", 0.0)

        met = self._evaluate_operator(total_value, operator, threshold)

        return met, {
            "reason": f"Total portfolio value: ${total_value:.2f}",
            "condition_type": "total_value",
            "total_value": total_value,
            "threshold": threshold,
            "operator": operator
        }

    def _check_total_change(
        self,
        portfolio: Dict[str, Any],
        operator: str,
        threshold: float
    ) -> tuple[bool, Dict[str, Any]]:
        """
        Check if total portfolio change meets threshold.

        Returns:
            tuple: (met, details_dict)
        """
        total_change_pct = portfolio.get("total_change_pct", 0.0)

        met = self._evaluate_operator(abs(total_change_pct), operator, threshold)

        return met, {
            "reason": f"Total portfolio change: {total_change_pct:.2f}%",
            "condition_type": "total_change",
            "total_change_pct": total_change_pct,
            "threshold": threshold,
            "operator": operator
        }

    def _evaluate_operator(self, current: float, operator: str, threshold: float) -> bool:
        """Evaluate comparison operator."""
        if operator == '<':
            return current < threshold
        elif operator == '>':
            return current > threshold
        elif operator == '<=':
            return current <= threshold
        elif operator == '>=':
            return current >= threshold
        return False


# ============================================================================
# Silence Evaluator
# ============================================================================

class SilenceEvaluator(Evaluator):
    """
    Evaluates user inactivity conditions using Redis activity tracking.

    Expression format: "silence OPERATOR DURATION"
    Examples: "silence > 4h", "silence >= 2d", "silence > 30m"

    Features:
    - Checks Redis for last activity timestamp
    - Supports hours (h), days (d), minutes (m)
    - Fail-safe: returns False on any error
    """

    # Activity key pattern (matches ActivityTracker module)
    ACTIVITY_KEY_PATTERN = "activity:{user_id}:last_message"

    # Expression parsing regex: "silence OPERATOR DURATION"
    EXPRESSION_PATTERN = re.compile(r'silence\s*([<>]=?)\s*(\d+)(h|d|m)')

    @observe(name="silence_evaluator", as_type="span")
    async def evaluate(self, expression: str, user_id: str) -> EvaluatorResult:
        """
        Evaluate silence condition.

        Args:
            expression: Silence expression (e.g., "silence > 4h")
            user_id: User identifier

        Returns:
            EvaluatorResult with met status and silence data
        """
        start_time = time.time()

        try:
            # Parse expression
            operator, duration = self._parse_expression(expression)

            # Get last activity timestamp
            last_activity = await self._get_last_activity(user_id)

            if last_activity is None:
                # No activity recorded - fail-safe (return False)
                logger.warning(
                    "No activity timestamp found - failing safe (returning False)",
                    extra={
                        "expression": expression,
                        "user_id": user_id,
                        "duration_ms": round((time.time() - start_time) * 1000, 2)
                    }
                )
                return EvaluatorResult(
                    met=False,
                    reason="No activity timestamp found",
                    data={"duration_threshold": duration.total_seconds()}
                )

            # Calculate silence duration
            now = datetime.utcnow()
            silence_duration = now - last_activity

            # Evaluate condition
            met = self._evaluate_operator(silence_duration, operator, duration)

            duration_ms = round((time.time() - start_time) * 1000, 2)

            logger.info(
                "Silence condition evaluated",
                extra={
                    "silence_hours": round(silence_duration.total_seconds() / 3600, 2),
                    "threshold_hours": round(duration.total_seconds() / 3600, 2),
                    "operator": operator,
                    "met": met,
                    "last_activity": last_activity.isoformat(),
                    "expression": expression,
                    "user_id": user_id,
                    "duration_ms": duration_ms
                }
            )

            return EvaluatorResult(
                met=met,
                reason=f"Silent for {self._format_duration(silence_duration)} "
                       f"(threshold: {operator} {self._format_duration(duration)})",
                data={
                    "silence_seconds": silence_duration.total_seconds(),
                    "silence_hours": silence_duration.total_seconds() / 3600,
                    "threshold_seconds": duration.total_seconds(),
                    "last_activity": last_activity.isoformat(),
                    "operator": operator
                }
            )

        except ValueError as e:
            # Expression parsing error - fail-safe
            logger.error(
                "Failed to parse silence expression - failing safe",
                extra={
                    "expression": expression,
                    "error": str(e),
                    "user_id": user_id,
                    "duration_ms": round((time.time() - start_time) * 1000, 2)
                }
            )
            return EvaluatorResult(
                met=False,
                reason=f"Invalid expression: {str(e)}",
                data={"expression": expression}
            )

        except Exception as e:
            # Unexpected error - fail-safe
            logger.error(
                "Unexpected error in silence evaluator - failing safe",
                extra={
                    "expression": expression,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "user_id": user_id,
                    "duration_ms": round((time.time() - start_time) * 1000, 2)
                }
            )
            return EvaluatorResult(
                met=False,
                reason=f"Error evaluating silence condition: {str(e)}",
                data={"expression": expression}
            )

    def _parse_expression(self, expression: str) -> tuple[str, timedelta]:
        """
        Parse silence expression into components.

        Args:
            expression: Silence expression (e.g., "silence > 4h")

        Returns:
            tuple: (operator, duration_timedelta)

        Raises:
            ValueError: If expression is invalid
        """
        match = self.EXPRESSION_PATTERN.match(expression.strip())
        if not match:
            raise ValueError(
                f"Invalid silence expression format. Expected 'silence OPERATOR DURATION' "
                f"(e.g., 'silence > 4h'), got: {expression}"
            )

        operator, value_str, unit = match.groups()

        # Parse duration value
        try:
            value = int(value_str)
        except ValueError:
            raise ValueError(f"Invalid duration value: {value_str}")

        # Convert to timedelta
        if unit == 'h':
            duration = timedelta(hours=value)
        elif unit == 'd':
            duration = timedelta(days=value)
        elif unit == 'm':
            duration = timedelta(minutes=value)
        else:
            raise ValueError(f"Invalid duration unit: {unit}")

        # Validate operator
        if operator not in ['<', '>', '<=', '>=']:
            raise ValueError(f"Invalid operator: {operator}")

        return operator, duration

    async def _get_last_activity(self, user_id: str) -> Optional[datetime]:
        """
        Get last activity timestamp from Redis.

        Args:
            user_id: User identifier

        Returns:
            Last activity datetime or None if not found
        """
        try:
            redis_client = await self._get_redis_client()
            key = self.ACTIVITY_KEY_PATTERN.format(user_id=user_id)
            timestamp_str = await redis_client.get(key)

            if timestamp_str:
                # Parse ISO format timestamp
                return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))

        except Exception as e:
            logger.warning(
                f"Failed to get last activity for user {user_id}: {e}",
                extra={"user_id": user_id, "error": str(e)}
            )

        return None

    def _evaluate_operator(self, current: timedelta, operator: str, threshold: timedelta) -> bool:
        """Evaluate comparison operator on timedeltas."""
        if operator == '<':
            return current < threshold
        elif operator == '>':
            return current > threshold
        elif operator == '<=':
            return current <= threshold
        elif operator == '>=':
            return current >= threshold
        return False

    def _format_duration(self, duration: timedelta) -> str:
        """Format timedelta as human-readable string."""
        total_seconds = duration.total_seconds()

        if total_seconds < 3600:  # Less than 1 hour
            minutes = int(total_seconds / 60)
            return f"{minutes}m"
        elif total_seconds < 86400:  # Less than 1 day
            hours = round(total_seconds / 3600, 1)
            return f"{hours}h"
        else:
            days = round(total_seconds / 86400, 1)
            return f"{days}d"


# ============================================================================
# Evaluator Factory
# ============================================================================

def get_evaluator(condition_type: str) -> Evaluator:
    """
    Factory function to get appropriate evaluator for condition type.

    Args:
        condition_type: Type of condition ("price", "portfolio", "silence")

    Returns:
        Evaluator instance

    Raises:
        ValueError: If condition_type is unknown
    """
    evaluators = {
        "price": PriceEvaluator,
        "portfolio": PortfolioEvaluator,
        "silence": SilenceEvaluator,
    }

    evaluator_class = evaluators.get(condition_type.lower())
    if evaluator_class is None:
        raise ValueError(
            f"Unknown condition type: {condition_type}. "
            f"Valid types: {', '.join(evaluators.keys())}"
        )

    return evaluator_class()


# ============================================================================
# Convenience Function
# ============================================================================

@observe(name="evaluate_condition", as_type="span")
async def evaluate_condition(
    condition_type: str,
    expression: str,
    user_id: str
) -> EvaluatorResult:
    """
    Convenience function to evaluate a condition.

    Automatically selects the appropriate evaluator and handles cleanup.

    Args:
        condition_type: Type of condition ("price", "portfolio", "silence")
        expression: Condition expression to evaluate
        user_id: User identifier

    Returns:
        EvaluatorResult with met status and details
    """
    evaluator = get_evaluator(condition_type)

    try:
        result = await evaluator.evaluate(expression, user_id)
        return result
    finally:
        # Clean up Redis connection
        await evaluator.close()
