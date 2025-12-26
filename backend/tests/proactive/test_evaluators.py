"""
Tests for Condition Evaluators - Price, Portfolio, and Silence evaluators.

Tests:
- PriceEvaluator with yfinance integration
- PortfolioEvaluator with MCP tool integration
- SilenceEvaluator with Redis activity tracking
- Factory function and convenience function
- Error handling and fail-safe behavior
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime, timedelta, timezone

from api.proactive.evaluators import (
    EvaluatorResult,
    Evaluator,
    PriceEvaluator,
    PortfolioEvaluator,
    SilenceEvaluator,
    get_evaluator,
    evaluate_condition,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_redis():
    """Mock async Redis client."""
    return AsyncMock()


# ============================================================================
# EvaluatorResult Tests
# ============================================================================

def test_evaluator_result_creation():
    """Test EvaluatorResult dataclass creation."""
    result = EvaluatorResult(
        met=True,
        reason="NVDA at $125 (threshold: < $130)",
        data={"current_price": 125.0, "threshold": 130.0}
    )

    assert result.met is True
    assert "NVDA" in result.reason
    assert result.data["current_price"] == 125.0


def test_evaluator_result_default_data():
    """Test EvaluatorResult with default empty data."""
    result = EvaluatorResult(met=False, reason="Test")

    assert result.data == {}


# ============================================================================
# Factory Function Tests
# ============================================================================

def test_get_evaluator_price():
    """Test factory returns PriceEvaluator."""
    evaluator = get_evaluator("price")
    assert isinstance(evaluator, PriceEvaluator)


def test_get_evaluator_portfolio():
    """Test factory returns PortfolioEvaluator."""
    evaluator = get_evaluator("portfolio")
    assert isinstance(evaluator, PortfolioEvaluator)


def test_get_evaluator_silence():
    """Test factory returns SilenceEvaluator."""
    evaluator = get_evaluator("silence")
    assert isinstance(evaluator, SilenceEvaluator)


def test_get_evaluator_unknown_raises():
    """Test factory raises for unknown type."""
    with pytest.raises(ValueError, match="Unknown condition type"):
        get_evaluator("unknown")


def test_get_evaluator_case_insensitive():
    """Test factory is case insensitive."""
    assert isinstance(get_evaluator("PRICE"), PriceEvaluator)
    assert isinstance(get_evaluator("Price"), PriceEvaluator)


# ============================================================================
# PriceEvaluator Tests
# ============================================================================

@pytest.mark.asyncio
async def test_price_evaluator_less_than_true():
    """Test price < threshold when condition is met."""
    evaluator = PriceEvaluator()

    with patch.object(evaluator, '_fetch_price_with_retry') as mock_fetch:
        mock_fetch.return_value = 125.0  # Current price

        result = await evaluator.evaluate("NVDA < 130", "user_123")

        assert result.met is True
        assert result.data["current_price"] == 125.0
        assert result.data["threshold"] == 130.0


@pytest.mark.asyncio
async def test_price_evaluator_less_than_false():
    """Test price < threshold when condition is NOT met."""
    evaluator = PriceEvaluator()

    with patch.object(evaluator, '_fetch_price_with_retry') as mock_fetch:
        mock_fetch.return_value = 135.0  # Current price above threshold

        result = await evaluator.evaluate("NVDA < 130", "user_123")

        assert result.met is False


@pytest.mark.asyncio
async def test_price_evaluator_greater_than():
    """Test price > threshold."""
    evaluator = PriceEvaluator()

    with patch.object(evaluator, '_fetch_price_with_retry') as mock_fetch:
        mock_fetch.return_value = 200.0

        result = await evaluator.evaluate("AAPL > 180", "user_123")

        assert result.met is True


@pytest.mark.asyncio
async def test_price_evaluator_less_than_or_equal():
    """Test price <= threshold at boundary."""
    evaluator = PriceEvaluator()

    with patch.object(evaluator, '_fetch_price_with_retry') as mock_fetch:
        mock_fetch.return_value = 130.0  # Exactly at threshold

        result = await evaluator.evaluate("NVDA <= 130", "user_123")

        assert result.met is True


@pytest.mark.asyncio
async def test_price_evaluator_greater_than_or_equal():
    """Test price >= threshold at boundary."""
    evaluator = PriceEvaluator()

    with patch.object(evaluator, '_fetch_price_with_retry') as mock_fetch:
        mock_fetch.return_value = 180.0

        result = await evaluator.evaluate("AAPL >= 180", "user_123")

        assert result.met is True


@pytest.mark.asyncio
async def test_price_evaluator_fetch_failure_returns_false():
    """Test fail-safe: returns False when price fetch fails."""
    evaluator = PriceEvaluator()

    with patch.object(evaluator, '_fetch_price_with_retry') as mock_fetch:
        mock_fetch.return_value = None  # Fetch failed

        result = await evaluator.evaluate("NVDA < 130", "user_123")

        assert result.met is False
        assert "Failed" in result.reason


@pytest.mark.asyncio
async def test_price_evaluator_invalid_expression():
    """Test invalid expression returns False."""
    evaluator = PriceEvaluator()

    result = await evaluator.evaluate("invalid expression", "user_123")

    assert result.met is False
    assert "Invalid" in result.reason


# ============================================================================
# PortfolioEvaluator Tests
# ============================================================================

@pytest.mark.asyncio
async def test_portfolio_evaluator_any_holding_change():
    """Test any_holding_change expression."""
    evaluator = PortfolioEvaluator()

    with patch.object(evaluator, '_fetch_portfolio') as mock_fetch:
        mock_fetch.return_value = {
            "holdings": [
                {"ticker": "AAPL", "change_pct": 2.5},
                {"ticker": "NVDA", "change_pct": 8.0},  # Max change
                {"ticker": "TSLA", "change_pct": -3.0},
            ],
            "total_value": 100000
        }

        result = await evaluator.evaluate("any_holding_change > 5%", "user_123")

        assert result.met is True
        assert result.data["max_change"] == 8.0
        assert result.data["max_change_ticker"] == "NVDA"


@pytest.mark.asyncio
async def test_portfolio_evaluator_any_holding_down():
    """Test any_holding_down expression."""
    evaluator = PortfolioEvaluator()

    with patch.object(evaluator, '_fetch_portfolio') as mock_fetch:
        mock_fetch.return_value = {
            "holdings": [
                {"ticker": "AAPL", "change_pct": 2.5},
                {"ticker": "NVDA", "change_pct": -7.0},  # Down 7%
                {"ticker": "TSLA", "change_pct": -3.0},
            ]
        }

        result = await evaluator.evaluate("any_holding_down > 5%", "user_123")

        assert result.met is True
        assert result.data["max_down"] == 7.0


@pytest.mark.asyncio
async def test_portfolio_evaluator_total_value():
    """Test total_value expression."""
    evaluator = PortfolioEvaluator()

    with patch.object(evaluator, '_fetch_portfolio') as mock_fetch:
        mock_fetch.return_value = {"total_value": 150000}

        result = await evaluator.evaluate("total_value >= 100000", "user_123")

        assert result.met is True
        assert result.data["total_value"] == 150000


@pytest.mark.asyncio
async def test_portfolio_evaluator_total_change():
    """Test total_change expression."""
    evaluator = PortfolioEvaluator()

    with patch.object(evaluator, '_fetch_portfolio') as mock_fetch:
        mock_fetch.return_value = {"total_change_pct": 6.5}

        result = await evaluator.evaluate("total_change > 5%", "user_123")

        assert result.met is True


@pytest.mark.asyncio
async def test_portfolio_evaluator_fetch_failure():
    """Test fail-safe: returns False when portfolio fetch fails."""
    evaluator = PortfolioEvaluator()

    with patch.object(evaluator, '_fetch_portfolio') as mock_fetch:
        mock_fetch.return_value = None

        result = await evaluator.evaluate("any_holding_change > 5%", "user_123")

        assert result.met is False


@pytest.mark.asyncio
async def test_portfolio_evaluator_condition_not_met():
    """Test when condition is NOT met."""
    evaluator = PortfolioEvaluator()

    with patch.object(evaluator, '_fetch_portfolio') as mock_fetch:
        mock_fetch.return_value = {
            "holdings": [
                {"ticker": "AAPL", "change_pct": 1.0},
                {"ticker": "NVDA", "change_pct": 2.0},
            ]
        }

        result = await evaluator.evaluate("any_holding_change > 5%", "user_123")

        assert result.met is False


# ============================================================================
# SilenceEvaluator Tests
# ============================================================================

@pytest.mark.asyncio
async def test_silence_evaluator_condition_met():
    """Test silence > threshold when user has been inactive."""
    evaluator = SilenceEvaluator()

    # User was last active 5 hours ago (use naive datetime to match evaluator)
    from datetime import datetime as dt
    last_activity = dt.utcnow() - timedelta(hours=5)

    with patch.object(evaluator, '_get_last_activity') as mock_get:
        mock_get.return_value = last_activity

        result = await evaluator.evaluate("silence > 4h", "user_123")

        assert result.met is True
        assert result.data["silence_hours"] > 4


@pytest.mark.asyncio
async def test_silence_evaluator_condition_not_met():
    """Test silence > threshold when user has been active recently."""
    evaluator = SilenceEvaluator()

    # User was last active 2 hours ago (use naive datetime to match evaluator)
    from datetime import datetime as dt
    last_activity = dt.utcnow() - timedelta(hours=2)

    with patch.object(evaluator, '_get_last_activity') as mock_get:
        mock_get.return_value = last_activity

        result = await evaluator.evaluate("silence > 4h", "user_123")

        assert result.met is False


@pytest.mark.asyncio
async def test_silence_evaluator_minutes():
    """Test silence with minutes unit."""
    evaluator = SilenceEvaluator()

    # Use naive datetime to match evaluator
    from datetime import datetime as dt
    last_activity = dt.utcnow() - timedelta(minutes=45)

    with patch.object(evaluator, '_get_last_activity') as mock_get:
        mock_get.return_value = last_activity

        result = await evaluator.evaluate("silence > 30m", "user_123")

        assert result.met is True


@pytest.mark.asyncio
async def test_silence_evaluator_days():
    """Test silence with days unit."""
    evaluator = SilenceEvaluator()

    # Use naive datetime to match evaluator
    from datetime import datetime as dt
    last_activity = dt.utcnow() - timedelta(days=3)

    with patch.object(evaluator, '_get_last_activity') as mock_get:
        mock_get.return_value = last_activity

        result = await evaluator.evaluate("silence > 2d", "user_123")

        assert result.met is True


@pytest.mark.asyncio
async def test_silence_evaluator_no_activity_record():
    """Test fail-safe: returns False when no activity timestamp found."""
    evaluator = SilenceEvaluator()

    with patch.object(evaluator, '_get_last_activity') as mock_get:
        mock_get.return_value = None

        result = await evaluator.evaluate("silence > 4h", "user_123")

        assert result.met is False


@pytest.mark.asyncio
async def test_silence_evaluator_invalid_expression():
    """Test invalid expression returns False."""
    evaluator = SilenceEvaluator()

    result = await evaluator.evaluate("invalid expression", "user_123")

    assert result.met is False
    assert "Invalid" in result.reason


# ============================================================================
# Convenience Function Tests
# ============================================================================

@pytest.mark.asyncio
async def test_evaluate_condition_price():
    """Test evaluate_condition with price type."""
    with patch.object(PriceEvaluator, 'evaluate') as mock_eval:
        with patch.object(PriceEvaluator, 'close') as mock_close:
            mock_eval.return_value = EvaluatorResult(met=True, reason="Price met")
            mock_close.return_value = None

            result = await evaluate_condition("price", "NVDA < 130", "user_123")

            assert result.met is True
            mock_close.assert_called_once()


@pytest.mark.asyncio
async def test_evaluate_condition_cleanup_on_error():
    """Test evaluate_condition cleans up on error."""
    with patch.object(PriceEvaluator, 'evaluate') as mock_eval:
        with patch.object(PriceEvaluator, 'close') as mock_close:
            mock_eval.side_effect = Exception("Test error")
            mock_close.return_value = None

            with pytest.raises(Exception, match="Test error"):
                await evaluate_condition("price", "NVDA < 130", "user_123")

            # Cleanup should still be called
            mock_close.assert_called_once()
