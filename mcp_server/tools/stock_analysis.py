"""
Stock Market Analysis Tools (Epic 10 - Story 10.6)

Provides tools for analyzing individual stocks including:
- Real-time price data and daily changes
- Fundamental metrics (P/E, market cap, dividend yield)
- Technical indicators (RSI, moving averages, trend)
- Historical price data with OHLCV
"""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import redis.asyncio as redis
import yfinance as yf

from mcp_server.config import get_config
from mcp_server.logging import get_logger
from .portfolio import normalize_ticker

logger = get_logger(__name__)

# Cache TTL for financial data: 24 hours (86400 seconds)
# Financial statements don't change intraday
FINANCIALS_CACHE_TTL = 86400


# =============================================================================
# Technical Analysis Helper Functions
# =============================================================================


def calculate_rsi(prices: pd.Series, period: int = 14) -> Optional[float]:
    """
    Calculate Relative Strength Index (RSI).

    Args:
        prices: Series of closing prices
        period: RSI period (default 14 days)

    Returns:
        RSI value (0-100) or None if insufficient data
    """
    if len(prices) < period + 1:
        return None

    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    # Avoid division by zero
    if loss.iloc[-1] == 0:
        return 100.0 if gain.iloc[-1] > 0 else 50.0

    rs = gain.iloc[-1] / loss.iloc[-1]
    rsi = 100 - (100 / (1 + rs))

    return round(rsi, 2)


def format_market_cap(market_cap: Optional[int]) -> Optional[str]:
    """
    Format market cap into human-readable string.

    Args:
        market_cap: Market capitalization in raw number

    Returns:
        Formatted string (e.g., "2.8T", "500B", "50M") or None
    """
    if market_cap is None:
        return None

    if market_cap >= 1_000_000_000_000:
        return f"{market_cap / 1_000_000_000_000:.1f}T"
    elif market_cap >= 1_000_000_000:
        return f"{market_cap / 1_000_000_000:.1f}B"
    elif market_cap >= 1_000_000:
        return f"{market_cap / 1_000_000:.1f}M"
    else:
        return str(market_cap)


def determine_trend(ma_50: Optional[float], ma_200: Optional[float], current_price: Optional[float]) -> str:
    """
    Determine trend based on moving averages.

    Args:
        ma_50: 50-day moving average
        ma_200: 200-day moving average
        current_price: Current stock price

    Returns:
        Trend string: "bullish", "bearish", or "neutral"
    """
    if ma_50 is None or ma_200 is None or current_price is None:
        return "neutral"

    # Golden cross: 50 MA above 200 MA = bullish
    # Death cross: 50 MA below 200 MA = bearish
    if ma_50 > ma_200 and current_price > ma_50:
        return "bullish"
    elif ma_50 < ma_200 and current_price < ma_50:
        return "bearish"
    else:
        return "neutral"


# =============================================================================
# Analyze Stock Tool
# =============================================================================


async def get_stock_data_tool_handler(
    ticker: str,
    include_technicals: bool = True,
    options_expiration: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analyze a stock and return comprehensive market data.

    Fetches real-time price data, fundamentals, optionally technical indicators,
    and optionally options chain data via Yahoo Finance.

    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL', 'GOOGL')
        include_technicals: Whether to include RSI, moving averages, trend analysis
        options_expiration: Options chain to fetch (default: None = no options)
            - None: Don't fetch options data
            - "nearest": Fetch the nearest available expiration
            - "YYYY-MM-DD": Fetch specific expiration (e.g., "2026-02-20")

    Returns:
        dict: Comprehensive stock analysis including price, fundamentals, technicals,
              and optionally options chain data
    """
    start_time = time.time()

    # Normalize ticker
    normalized_ticker = normalize_ticker(ticker)
    if normalized_ticker is None:
        logger.warning(
            "Invalid ticker format for get_stock_data",
            extra={"ticker": ticker}
        )
        return {
            "status": "error",
            "message": f"Invalid ticker format: '{ticker}'. Ticker must be 1-10 alphanumeric characters (e.g., AAPL, GOOGL, BRK.B)."
        }

    try:
        logger.info(
            "Analyzing stock via MCP tool",
            extra={
                "ticker": normalized_ticker,
                "include_technicals": include_technicals
            }
        )

        # Create yfinance Ticker object
        stock = yf.Ticker(normalized_ticker)

        # Get stock info (fundamentals)
        info = stock.info

        # Check if ticker is valid (yfinance returns empty info for invalid tickers)
        if not info or info.get("regularMarketPrice") is None:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning(
                "Stock not found",
                extra={
                    "ticker": normalized_ticker,
                    "duration_ms": duration_ms
                }
            )
            return {
                "status": "error",
                "message": f"Could not find stock data for ticker '{normalized_ticker}'. Please check the symbol and try again.",
                "ticker": normalized_ticker
            }

        # Extract basic price data
        current_price = info.get("regularMarketPrice") or info.get("currentPrice")
        previous_close = info.get("regularMarketPreviousClose") or info.get("previousClose")

        # Calculate daily change
        change_1d = None
        change_1d_pct = None
        if current_price and previous_close:
            change_1d = round(current_price - previous_close, 2)
            change_1d_pct = round((change_1d / previous_close) * 100, 2)

        # Build basic result
        result = {
            "status": "success",
            "ticker": normalized_ticker,
            "name": info.get("shortName") or info.get("longName"),
            "current_price": current_price,
            "previous_close": previous_close,
            "change_1d": change_1d,
            "change_1d_pct": change_1d_pct,
            "day_high": info.get("regularMarketDayHigh") or info.get("dayHigh"),
            "day_low": info.get("regularMarketDayLow") or info.get("dayLow"),
            "52_week_high": info.get("fiftyTwoWeekHigh"),
            "52_week_low": info.get("fiftyTwoWeekLow"),
            "market_cap": format_market_cap(info.get("marketCap")),
            "market_cap_raw": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "dividend_yield": info.get("dividendYield"),
            "volume": info.get("regularMarketVolume") or info.get("volume"),
            "avg_volume": info.get("averageVolume"),
            "exchange": info.get("exchange"),
            "currency": info.get("currency", "USD")
        }

        # Calculate volume analysis
        if result["volume"] and result["avg_volume"]:
            if result["volume"] > result["avg_volume"] * 1.2:
                result["volume_analysis"] = "above_average"
            elif result["volume"] < result["avg_volume"] * 0.8:
                result["volume_analysis"] = "below_average"
            else:
                result["volume_analysis"] = "average"
        else:
            result["volume_analysis"] = "unknown"

        # Add technical indicators if requested
        if include_technicals:
            try:
                # Get historical data for technical analysis (need ~200 days for 200 MA)
                history = stock.history(period="1y")

                if len(history) > 0:
                    close_prices = history["Close"]

                    # RSI (14-day)
                    result["rsi_14"] = calculate_rsi(close_prices, 14)

                    # Moving averages
                    if len(close_prices) >= 50:
                        result["ma_50"] = round(close_prices.rolling(window=50).mean().iloc[-1], 2)
                    else:
                        result["ma_50"] = None

                    if len(close_prices) >= 200:
                        result["ma_200"] = round(close_prices.rolling(window=200).mean().iloc[-1], 2)
                    else:
                        result["ma_200"] = None

                    # Trend determination
                    result["trend"] = determine_trend(
                        result.get("ma_50"),
                        result.get("ma_200"),
                        current_price
                    )

                    # Price vs 52-week range
                    if result["52_week_high"] and result["52_week_low"] and current_price:
                        range_size = result["52_week_high"] - result["52_week_low"]
                        if range_size > 0:
                            result["52_week_position"] = round(
                                ((current_price - result["52_week_low"]) / range_size) * 100, 1
                            )
                else:
                    result["rsi_14"] = None
                    result["ma_50"] = None
                    result["ma_200"] = None
                    result["trend"] = "unknown"

            except Exception as e:
                logger.warning(
                    "Failed to calculate technical indicators",
                    extra={
                        "ticker": normalized_ticker,
                        "error": str(e)
                    }
                )
                result["rsi_14"] = None
                result["ma_50"] = None
                result["ma_200"] = None
                result["trend"] = "unknown"

        # Add options chain data if requested
        if options_expiration is not None:
            try:
                # Get available expiration dates
                available_expirations = list(stock.options) if stock.options else []

                if not available_expirations:
                    result["options"] = {
                        "status": "unavailable",
                        "message": f"No options available for {normalized_ticker}",
                        "available_expirations": []
                    }
                else:
                    # Determine which expiration to fetch
                    target_expiration = None

                    if options_expiration.lower() == "nearest":
                        target_expiration = available_expirations[0]
                    elif options_expiration in available_expirations:
                        target_expiration = options_expiration
                    else:
                        # Try to find closest match
                        result["options"] = {
                            "status": "invalid_expiration",
                            "message": f"Expiration '{options_expiration}' not available",
                            "available_expirations": available_expirations
                        }
                        target_expiration = None

                    if target_expiration:
                        # Fetch the options chain
                        chain = stock.option_chain(target_expiration)

                        # Calculate days to expiry
                        exp_date = datetime.strptime(target_expiration, "%Y-%m-%d")
                        days_to_expiry = (exp_date - datetime.now()).days

                        # Process calls - get key fields, limit to reasonable strikes
                        calls_df = chain.calls
                        current = result.get("current_price", 0) or 0

                        # Filter to strikes within 30% of current price for relevance
                        if current > 0:
                            strike_min = current * 0.7
                            strike_max = current * 1.3
                            calls_df = calls_df[(calls_df["strike"] >= strike_min) & (calls_df["strike"] <= strike_max)]
                            puts_df = chain.puts[(chain.puts["strike"] >= strike_min) & (chain.puts["strike"] <= strike_max)]
                        else:
                            puts_df = chain.puts

                        # Convert to list of dicts with key fields
                        def format_options(df):
                            options_list = []
                            for _, row in df.iterrows():
                                opt = {
                                    "strike": float(row["strike"]),
                                    "bid": float(row["bid"]) if pd.notna(row["bid"]) else 0,
                                    "ask": float(row["ask"]) if pd.notna(row["ask"]) else 0,
                                    "last": float(row["lastPrice"]) if pd.notna(row["lastPrice"]) else 0,
                                    "volume": int(row["volume"]) if pd.notna(row["volume"]) else 0,
                                    "openInterest": int(row["openInterest"]) if pd.notna(row["openInterest"]) else 0,
                                    "impliedVolatility": round(float(row["impliedVolatility"]) * 100, 1) if pd.notna(row["impliedVolatility"]) else None,
                                    "inTheMoney": bool(row["inTheMoney"]) if pd.notna(row["inTheMoney"]) else False
                                }
                                # Calculate bid-ask spread
                                if opt["bid"] > 0 and opt["ask"] > 0:
                                    opt["spread"] = round(opt["ask"] - opt["bid"], 2)
                                    opt["spreadPct"] = round((opt["spread"] / opt["ask"]) * 100, 1)
                                options_list.append(opt)
                            return options_list

                        result["options"] = {
                            "status": "success",
                            "expiration": target_expiration,
                            "days_to_expiry": days_to_expiry,
                            "calls": format_options(calls_df),
                            "puts": format_options(puts_df),
                            "available_expirations": available_expirations
                        }

                        logger.info(
                            "Options chain fetched successfully",
                            extra={
                                "ticker": normalized_ticker,
                                "expiration": target_expiration,
                                "calls_count": len(result["options"]["calls"]),
                                "puts_count": len(result["options"]["puts"])
                            }
                        )

            except Exception as e:
                logger.warning(
                    "Failed to fetch options chain",
                    extra={
                        "ticker": normalized_ticker,
                        "options_expiration": options_expiration,
                        "error": str(e)
                    }
                )
                result["options"] = {
                    "status": "error",
                    "message": f"Failed to fetch options: {str(e)}",
                    "available_expirations": []
                }

        duration_ms = int((time.time() - start_time) * 1000)

        logger.info(
            "Stock analysis completed successfully",
            extra={
                "ticker": normalized_ticker,
                "current_price": current_price,
                "change_1d_pct": change_1d_pct,
                "duration_ms": duration_ms
            }
        )

        return result

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Error analyzing stock",
            extra={
                "ticker": normalized_ticker,
                "error": str(e),
                "duration_ms": duration_ms
            },
            exc_info=True
        )
        return {
            "status": "error",
            "message": f"Failed to analyze stock: {str(e)}",
            "ticker": normalized_ticker
        }


# Analyze stock tool definition
get_stock_data_tool = {
    "name": "get_stock_data",
    "description": """Analyze a stock and get comprehensive market data including current price, daily change, 52-week range, P/E ratio, market cap, volume, technical indicators (RSI, moving averages, trend), and optionally options chain data.""",
    "inputSchema": {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol (e.g., 'AAPL', 'GOOGL', 'TSLA', 'BRK.B')"
            },
            "include_technicals": {
                "type": "boolean",
                "description": "Whether to include technical indicators (RSI, moving averages, trend). Default: true",
                "default": True
            },
            "options_expiration": {
                "type": "string",
                "description": "Options chain expiration to fetch. Use 'nearest' for closest expiration, or a specific date like '2026-02-20'. Omit to skip options data."
            }
        },
        "required": ["ticker"]
    },
    "handler": get_stock_data_tool_handler
}


# =============================================================================
# Get Stock History Tool
# =============================================================================


async def get_stock_history_tool_handler(
    ticker: str,
    period: str = "1mo"
) -> Dict[str, Any]:
    """
    Get historical price data for a stock.

    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL', 'GOOGL')
        period: Time period - one of: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, max

    Returns:
        dict: Historical OHLCV data with summary statistics
    """
    start_time = time.time()

    # Normalize ticker
    normalized_ticker = normalize_ticker(ticker)
    if normalized_ticker is None:
        logger.warning(
            "Invalid ticker format for get_stock_history",
            extra={"ticker": ticker}
        )
        return {
            "status": "error",
            "message": f"Invalid ticker format: '{ticker}'. Ticker must be 1-10 alphanumeric characters."
        }

    # Validate period
    valid_periods = ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"]
    if period not in valid_periods:
        return {
            "status": "error",
            "message": f"Invalid period: '{period}'. Valid periods: {', '.join(valid_periods)}"
        }

    try:
        logger.info(
            "Getting stock history via MCP tool",
            extra={
                "ticker": normalized_ticker,
                "period": period
            }
        )

        # Create yfinance Ticker object
        stock = yf.Ticker(normalized_ticker)

        # Get historical data
        history = stock.history(period=period)

        if history.empty:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning(
                "No historical data found",
                extra={
                    "ticker": normalized_ticker,
                    "period": period,
                    "duration_ms": duration_ms
                }
            )
            return {
                "status": "error",
                "message": f"No historical data found for ticker '{normalized_ticker}'. Please check the symbol.",
                "ticker": normalized_ticker
            }

        # Convert to list of OHLCV records
        data_points = []
        for date, row in history.iterrows():
            data_points.append({
                "date": date.strftime("%Y-%m-%d"),
                "open": round(row["Open"], 2),
                "high": round(row["High"], 2),
                "low": round(row["Low"], 2),
                "close": round(row["Close"], 2),
                "volume": int(row["Volume"])
            })

        # Calculate summary statistics
        close_prices = history["Close"]
        start_price = close_prices.iloc[0]
        end_price = close_prices.iloc[-1]
        period_change = round(end_price - start_price, 2)
        period_change_pct = round((period_change / start_price) * 100, 2)

        duration_ms = int((time.time() - start_time) * 1000)

        logger.info(
            "Stock history retrieved successfully",
            extra={
                "ticker": normalized_ticker,
                "period": period,
                "data_points": len(data_points),
                "duration_ms": duration_ms
            }
        )

        return {
            "status": "success",
            "ticker": normalized_ticker,
            "period": period,
            "data_points": len(data_points),
            "summary": {
                "start_date": data_points[0]["date"],
                "end_date": data_points[-1]["date"],
                "start_price": round(start_price, 2),
                "end_price": round(end_price, 2),
                "period_change": period_change,
                "period_change_pct": period_change_pct,
                "period_high": round(close_prices.max(), 2),
                "period_low": round(close_prices.min(), 2),
                "avg_volume": int(history["Volume"].mean())
            },
            "history": data_points
        }

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Error getting stock history",
            extra={
                "ticker": normalized_ticker,
                "period": period,
                "error": str(e),
                "duration_ms": duration_ms
            },
            exc_info=True
        )
        return {
            "status": "error",
            "message": f"Failed to get stock history: {str(e)}",
            "ticker": normalized_ticker
        }


# Get stock history tool definition
get_stock_history_tool = {
    "name": "get_stock_history",
    "description": "Get historical price data for a stock. Returns daily OHLCV (Open, High, Low, Close, Volume) data for the specified time period. Use this when the user asks about price history, trends over time, or wants to see how a stock has performed over a specific period.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol (e.g., 'AAPL', 'GOOGL')"
            },
            "period": {
                "type": "string",
                "description": "Time period for history. Options: 1d (1 day), 5d (5 days), 1mo (1 month), 3mo (3 months), 6mo (6 months), 1y (1 year), 2y (2 years), 5y (5 years), max (all available). Default: 1mo",
                "enum": ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"],
                "default": "1mo"
            }
        },
        "required": ["ticker"]
    },
    "handler": get_stock_history_tool_handler
}


# =============================================================================
# Get Financials Tool (Financial Statements + Earnings)
# =============================================================================


def _safe_float(value, decimals: int = 2) -> Optional[float]:
    """Safely convert value to float, handling NaN/None."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return round(float(value), decimals)
    except (ValueError, TypeError):
        return None


def _format_large_number(value) -> Optional[str]:
    """Format large numbers with B/M suffix for readability."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        num = float(value)
        if abs(num) >= 1_000_000_000_000:
            return f"{num / 1_000_000_000_000:.2f}T"
        elif abs(num) >= 1_000_000_000:
            return f"{num / 1_000_000_000:.2f}B"
        elif abs(num) >= 1_000_000:
            return f"{num / 1_000_000:.2f}M"
        else:
            return f"{num:,.0f}"
    except (ValueError, TypeError):
        return None


def _extract_financial_row(df: pd.DataFrame, row_names: List[str]) -> List[Optional[float]]:
    """
    Extract a row from financial statement DataFrame by trying multiple row names.
    Returns list of values for each period (column).
    """
    if df is None or df.empty:
        return []

    for name in row_names:
        if name in df.index:
            row = df.loc[name]
            return [_safe_float(v) for v in row.values]
    return [None] * len(df.columns)


def _get_redis_client() -> Optional[redis.Redis]:
    """Create Redis client for caching."""
    try:
        config = get_config()
        redis_host = config.get("REDIS_HOST", "redis")
        redis_port = int(config.get("REDIS_PORT", 6379))
        return redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True
        )
    except Exception as e:
        logger.warning(f"Failed to create Redis client: {e}")
        return None


async def get_financials_tool_handler(
    ticker: str,
    include_statements: bool = True,
    include_earnings: bool = True,
    periods: str = "annual"
) -> Dict[str, Any]:
    """
    Get comprehensive financial data for a stock.

    Fetches financial statements (income statement, balance sheet, cash flow)
    and earnings data from Yahoo Finance. Data is cached for 24 hours.

    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL', 'GOOGL')
        include_statements: Include income statement, balance sheet, cash flow
        include_earnings: Include earnings dates and history
        periods: 'annual' or 'quarterly' for financial statements

    Returns:
        dict: Comprehensive financial data including statements and earnings
    """
    import json

    start_time = time.time()

    # Normalize ticker
    normalized_ticker = normalize_ticker(ticker)
    if normalized_ticker is None:
        logger.warning("Invalid ticker format for get_financials", extra={"ticker": ticker})
        return {
            "status": "error",
            "message": f"Invalid ticker format: '{ticker}'. Must be 1-10 alphanumeric characters."
        }

    # Validate periods
    if periods not in ["annual", "quarterly"]:
        return {
            "status": "error",
            "message": f"Invalid periods: '{periods}'. Must be 'annual' or 'quarterly'."
        }

    logger.info(
        "Fetching financial data",
        extra={
            "ticker": normalized_ticker,
            "periods": periods,
            "include_statements": include_statements,
            "include_earnings": include_earnings
        }
    )

    # Check cache first
    cache_key = f"financials:{normalized_ticker}:{periods}"
    redis_client = None
    cached_data = None

    try:
        redis_client = _get_redis_client()
        if redis_client:
            cached_json = await redis_client.get(cache_key)
            if cached_json:
                cached_data = json.loads(cached_json)
                logger.info(
                    "Financial data cache hit",
                    extra={"ticker": normalized_ticker, "cache_key": cache_key}
                )
    except Exception as e:
        logger.warning(f"Redis cache check failed: {e}")

    # Return cached data if available
    if cached_data:
        duration_ms = int((time.time() - start_time) * 1000)
        cached_data["from_cache"] = True
        cached_data["duration_ms"] = duration_ms
        if redis_client:
            await redis_client.close()
        return cached_data

    try:
        # Create yfinance Ticker object
        stock = yf.Ticker(normalized_ticker)
        info = stock.info

        # Validate ticker exists
        if not info or not info.get("shortName"):
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning("Ticker not found", extra={"ticker": normalized_ticker})
            if redis_client:
                await redis_client.close()
            return {
                "status": "error",
                "message": f"Could not find financial data for '{normalized_ticker}'.",
                "ticker": normalized_ticker,
                "duration_ms": duration_ms
            }

        result = {
            "status": "success",
            "ticker": normalized_ticker,
            "name": info.get("shortName") or info.get("longName"),
            "currency": info.get("currency", "USD"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "from_cache": False
        }

        # =================================================================
        # FINANCIAL STATEMENTS
        # =================================================================
        if include_statements:
            logger.debug("Fetching financial statements", extra={"ticker": normalized_ticker})

            try:
                # Get the appropriate statements based on period
                if periods == "annual":
                    income_df = stock.income_stmt
                    balance_df = stock.balance_sheet
                    cashflow_df = stock.cashflow
                else:
                    income_df = stock.quarterly_income_stmt
                    balance_df = stock.quarterly_balance_sheet
                    cashflow_df = stock.quarterly_cashflow

                # Extract period dates (columns)
                def get_period_labels(df: pd.DataFrame) -> List[str]:
                    if df is None or df.empty:
                        return []
                    return [col.strftime("%Y-%m-%d") if hasattr(col, 'strftime') else str(col)
                            for col in df.columns]

                # INCOME STATEMENT
                income_periods = get_period_labels(income_df)
                result["financials"] = {
                    "income_statement": {
                        "periods": income_periods,
                        "total_revenue": _extract_financial_row(income_df, ["Total Revenue", "Revenue"]),
                        "total_revenue_formatted": [_format_large_number(v) for v in _extract_financial_row(income_df, ["Total Revenue", "Revenue"])],
                        "cost_of_revenue": _extract_financial_row(income_df, ["Cost Of Revenue", "Cost of Revenue"]),
                        "gross_profit": _extract_financial_row(income_df, ["Gross Profit"]),
                        "gross_profit_formatted": [_format_large_number(v) for v in _extract_financial_row(income_df, ["Gross Profit"])],
                        "operating_income": _extract_financial_row(income_df, ["Operating Income", "EBIT"]),
                        "operating_income_formatted": [_format_large_number(v) for v in _extract_financial_row(income_df, ["Operating Income", "EBIT"])],
                        "net_income": _extract_financial_row(income_df, ["Net Income", "Net Income Common Stockholders"]),
                        "net_income_formatted": [_format_large_number(v) for v in _extract_financial_row(income_df, ["Net Income", "Net Income Common Stockholders"])],
                        "eps_basic": _extract_financial_row(income_df, ["Basic EPS"]),
                        "eps_diluted": _extract_financial_row(income_df, ["Diluted EPS"]),
                        "ebitda": _extract_financial_row(income_df, ["EBITDA", "Normalized EBITDA"]),
                        "ebitda_formatted": [_format_large_number(v) for v in _extract_financial_row(income_df, ["EBITDA", "Normalized EBITDA"])]
                    }
                }

                # BALANCE SHEET
                balance_periods = get_period_labels(balance_df)
                result["financials"]["balance_sheet"] = {
                    "periods": balance_periods,
                    "total_assets": _extract_financial_row(balance_df, ["Total Assets"]),
                    "total_assets_formatted": [_format_large_number(v) for v in _extract_financial_row(balance_df, ["Total Assets"])],
                    "total_liabilities": _extract_financial_row(balance_df, ["Total Liabilities Net Minority Interest", "Total Liabilities"]),
                    "total_liabilities_formatted": [_format_large_number(v) for v in _extract_financial_row(balance_df, ["Total Liabilities Net Minority Interest", "Total Liabilities"])],
                    "total_debt": _extract_financial_row(balance_df, ["Total Debt", "Long Term Debt"]),
                    "total_debt_formatted": [_format_large_number(v) for v in _extract_financial_row(balance_df, ["Total Debt", "Long Term Debt"])],
                    "cash_and_equivalents": _extract_financial_row(balance_df, ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"]),
                    "cash_formatted": [_format_large_number(v) for v in _extract_financial_row(balance_df, ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"])],
                    "shareholders_equity": _extract_financial_row(balance_df, ["Stockholders Equity", "Total Equity Gross Minority Interest"]),
                    "shareholders_equity_formatted": [_format_large_number(v) for v in _extract_financial_row(balance_df, ["Stockholders Equity", "Total Equity Gross Minority Interest"])]
                }

                # CASH FLOW
                cashflow_periods = get_period_labels(cashflow_df)
                operating_cf = _extract_financial_row(cashflow_df, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"])
                capex = _extract_financial_row(cashflow_df, ["Capital Expenditure", "Purchase Of PPE"])

                # Calculate Free Cash Flow = Operating CF - CapEx
                free_cash_flow = []
                for i in range(max(len(operating_cf), len(capex))):
                    ocf = operating_cf[i] if i < len(operating_cf) else None
                    cap = capex[i] if i < len(capex) else None
                    if ocf is not None and cap is not None:
                        # CapEx is usually negative, so we add it (subtracting negative = adding)
                        fcf = ocf + cap if cap < 0 else ocf - abs(cap)
                        free_cash_flow.append(_safe_float(fcf))
                    else:
                        free_cash_flow.append(None)

                result["financials"]["cash_flow"] = {
                    "periods": cashflow_periods,
                    "operating_cash_flow": operating_cf,
                    "operating_cash_flow_formatted": [_format_large_number(v) for v in operating_cf],
                    "capital_expenditure": capex,
                    "free_cash_flow": free_cash_flow,
                    "free_cash_flow_formatted": [_format_large_number(v) for v in free_cash_flow],
                    "dividends_paid": _extract_financial_row(cashflow_df, ["Cash Dividends Paid", "Common Stock Dividend Paid"]),
                    "stock_repurchases": _extract_financial_row(cashflow_df, ["Repurchase Of Capital Stock", "Common Stock Payments"])
                }

                logger.info(
                    "Financial statements extracted",
                    extra={
                        "ticker": normalized_ticker,
                        "income_periods": len(income_periods),
                        "balance_periods": len(balance_periods),
                        "cashflow_periods": len(cashflow_periods)
                    }
                )

            except Exception as e:
                logger.warning(
                    "Failed to extract financial statements",
                    extra={"ticker": normalized_ticker, "error": str(e)}
                )
                result["financials"] = {"error": f"Failed to fetch statements: {str(e)}"}

        # =================================================================
        # EARNINGS DATA
        # =================================================================
        if include_earnings:
            logger.debug("Fetching earnings data", extra={"ticker": normalized_ticker})

            try:
                earnings_result = {
                    "next_earnings_date": None,
                    "history": []
                }

                # Get earnings dates
                try:
                    earnings_dates = stock.earnings_dates
                    if earnings_dates is not None and not earnings_dates.empty:
                        # Find next earnings date (future dates)
                        now = pd.Timestamp.now(tz='UTC')
                        future_dates = earnings_dates[earnings_dates.index > now]
                        if not future_dates.empty:
                            next_date = future_dates.index[0]
                            earnings_result["next_earnings_date"] = next_date.strftime("%Y-%m-%d")

                        # Get earnings history (past dates with EPS data)
                        past_dates = earnings_dates[earnings_dates.index <= now].head(8)
                        for date, row in past_dates.iterrows():
                            eps_actual = _safe_float(row.get("Reported EPS"))
                            eps_estimate = _safe_float(row.get("EPS Estimate"))

                            surprise_pct = None
                            if eps_actual is not None and eps_estimate is not None and eps_estimate != 0:
                                surprise_pct = _safe_float(((eps_actual - eps_estimate) / abs(eps_estimate)) * 100, 1)

                            earnings_result["history"].append({
                                "date": date.strftime("%Y-%m-%d"),
                                "eps_actual": eps_actual,
                                "eps_estimate": eps_estimate,
                                "surprise_pct": surprise_pct
                            })
                except Exception as e:
                    logger.warning(f"Failed to get earnings dates: {e}")

                result["earnings"] = earnings_result

                logger.info(
                    "Earnings data extracted",
                    extra={
                        "ticker": normalized_ticker,
                        "next_earnings": earnings_result["next_earnings_date"],
                        "history_count": len(earnings_result["history"])
                    }
                )

            except Exception as e:
                logger.warning(
                    "Failed to extract earnings data",
                    extra={"ticker": normalized_ticker, "error": str(e)}
                )
                result["earnings"] = {"error": f"Failed to fetch earnings: {str(e)}"}

        # =================================================================
        # CACHE THE RESULT
        # =================================================================
        duration_ms = int((time.time() - start_time) * 1000)
        result["duration_ms"] = duration_ms

        try:
            if redis_client:
                await redis_client.setex(
                    cache_key,
                    FINANCIALS_CACHE_TTL,
                    json.dumps(result)
                )
                logger.info(
                    "Financial data cached",
                    extra={"ticker": normalized_ticker, "cache_key": cache_key, "ttl": FINANCIALS_CACHE_TTL}
                )
        except Exception as e:
            logger.warning(f"Failed to cache financial data: {e}")

        logger.info(
            "Financial data retrieval completed",
            extra={
                "ticker": normalized_ticker,
                "duration_ms": duration_ms,
                "include_statements": include_statements,
                "include_earnings": include_earnings
            }
        )

        return result

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Error fetching financial data",
            extra={"ticker": normalized_ticker, "error": str(e), "duration_ms": duration_ms},
            exc_info=True
        )
        return {
            "status": "error",
            "message": f"Failed to get financial data: {str(e)}",
            "ticker": normalized_ticker,
            "duration_ms": duration_ms
        }
    finally:
        if redis_client:
            try:
                await redis_client.close()
            except Exception:
                pass


# Get financials tool definition
get_financials_tool = {
    "name": "get_financials",
    "description": (
        "Get comprehensive financial data for a stock including financial statements "
        "(income statement, balance sheet, cash flow) and earnings history. "
        "Use this for fundamental analysis: revenue trends, profitability, debt levels, "
        "cash flow generation, and earnings performance. Data is cached for 24 hours."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol (e.g., 'AAPL', 'GOOGL', 'MSFT')"
            },
            "include_statements": {
                "type": "boolean",
                "description": "Include income statement, balance sheet, and cash flow. Default: true",
                "default": True
            },
            "include_earnings": {
                "type": "boolean",
                "description": "Include earnings dates and historical EPS data. Default: true",
                "default": True
            },
            "periods": {
                "type": "string",
                "description": "Period type for financial statements: 'annual' or 'quarterly'. Default: annual",
                "enum": ["annual", "quarterly"],
                "default": "annual"
            }
        },
        "required": ["ticker"]
    },
    "handler": get_financials_tool_handler
}
