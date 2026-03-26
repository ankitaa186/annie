"""
MCP Portfolio Management Tools (Epic 10)

This module provides portfolio management tools for tracking and managing
user investment holdings, including:
- get_portfolio: Retrieve user portfolio with optional price enrichment
- add_holding: Add or update a stock holding (UPSERT behavior)
- update_holding: Update an existing holding
- remove_holding: Remove a single holding
- clear_portfolio: Remove all holdings (requires confirmation)

All tools communicate with the agentic-memories service for persistent storage
and use Redis for price caching.
"""

import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
import redis.asyncio as redis
import yfinance as yf
import pandas as pd

from mcp_server.config import get_config
from mcp_server.logging import get_logger

logger = get_logger(__name__)

# =============================================================================
# Constants and Utilities
# =============================================================================

# Price cache TTL: 15 minutes (900 seconds)
PRICE_CACHE_TTL = 900

# Ticker validation pattern: 1-10 uppercase alphanumeric + dots (for BRK.B style)
TICKER_PATTERN = re.compile(r'^[A-Z0-9\.]{1,10}$')


def normalize_ticker(ticker: str) -> Optional[str]:
    """
    Normalize ticker to uppercase and validate format.

    Converts hyphens to dots (BRK-B -> BRK.B) for yfinance compatibility.

    Args:
        ticker: Stock ticker symbol (e.g., 'aapl', 'GOOGL', 'BRK.B', 'BRK-B')

    Returns:
        Normalized uppercase ticker or None if invalid
    """
    if not ticker:
        return None

    # Uppercase, strip whitespace, convert hyphens to dots (BRK-B -> BRK.B)
    normalized = ticker.upper().strip().replace('-', '.')

    if not normalized:
        return None

    if not TICKER_PATTERN.match(normalized):
        logger.warning(f"Invalid ticker format rejected: {ticker}")
        return None

    return normalized


async def batch_fetch_prices_with_cache(
    tickers: list,
    redis_client: Optional[redis.Redis] = None
) -> tuple[Dict[str, float], list]:
    """
    Fetch current prices for multiple tickers with Redis caching.

    Uses single batch call to yfinance for uncached tickers.
    Caches fetched prices in Redis with 15-minute TTL.

    Args:
        tickers: List of ticker symbols (already normalized to uppercase)
        redis_client: Optional Redis client. Creates new connection if not provided.

    Returns:
        tuple: (prices_dict, failed_tickers_list)
            - prices_dict: {ticker: price} for successful fetches
            - failed_tickers_list: tickers that failed to fetch
    """
    if not tickers:
        return {}, []

    prices = {}
    failed_tickers = []
    tickers_to_fetch = []

    # Get Redis connection
    own_redis = False
    if redis_client is None:
        try:
            config = get_config()
            redis_host = config.get("REDIS_HOST", "redis")
            redis_port = int(config.get("REDIS_PORT", 6379))
            redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                decode_responses=True
            )
            own_redis = True
        except Exception as e:
            logger.warning(f"Failed to connect to Redis for price caching: {e}")
            redis_client = None

    # Check cache for each ticker
    for ticker in tickers:
        if redis_client:
            try:
                cache_key = f"stock_price:{ticker}"
                cached_price = await redis_client.get(cache_key)
                if cached_price:
                    prices[ticker] = float(cached_price)
                    logger.debug(f"Price cache hit for {ticker}: {cached_price}")
                    continue
            except Exception as e:
                logger.warning(f"Redis cache check failed for {ticker}: {e}")

        tickers_to_fetch.append(ticker)

    # Batch fetch uncached tickers from yfinance
    if tickers_to_fetch:
        try:
            logger.info(
                "Batch fetching prices from yfinance",
                extra={
                    "tickers": tickers_to_fetch,
                    "count": len(tickers_to_fetch)
                }
            )

            # Single batch call to yfinance
            data = yf.download(
                tickers_to_fetch,
                period="1d",
                progress=False,
                threads=True
            )

            # Check if we got any data
            if data.empty:
                logger.warning("yfinance returned empty DataFrame")
                failed_tickers.extend(tickers_to_fetch)
            else:
                # Handle both single and multi-ticker response formats
                # yfinance returns different column structures:
                # - Single ticker: columns are ['Open', 'High', 'Low', 'Close', 'Volume']
                # - Multiple tickers: MultiIndex columns like [('Close', 'AAPL'), ('Close', 'GOOGL')]

                has_multiindex = isinstance(data.columns, pd.MultiIndex)

                for ticker in tickers_to_fetch:
                    try:
                        price = None

                        if has_multiindex:
                            # Multi-ticker format: access via ('Close', ticker)
                            if ('Close', ticker) in data.columns:
                                price_series = data[('Close', ticker)]
                                if not price_series.empty:
                                    price = price_series.iloc[-1]
                        else:
                            # Single ticker format: access via 'Close'
                            if 'Close' in data.columns:
                                price_series = data['Close']
                                if not price_series.empty:
                                    price = price_series.iloc[-1]

                        if price is not None and pd.notna(price):
                            prices[ticker] = round(float(price), 2)
                            # Cache the price
                            if redis_client:
                                try:
                                    await redis_client.setex(
                                        f"stock_price:{ticker}",
                                        PRICE_CACHE_TTL,
                                        str(prices[ticker])
                                    )
                                except Exception as e:
                                    logger.warning(f"Failed to cache price for {ticker}: {e}")
                        else:
                            failed_tickers.append(ticker)

                    except Exception as e:
                        logger.warning(f"Failed to parse price for {ticker}: {e}")
                        failed_tickers.append(ticker)

            logger.info(
                "Batch price fetch completed",
                extra={
                    "fetched_count": len(tickers_to_fetch) - len([t for t in failed_tickers if t in tickers_to_fetch]),
                    "failed_count": len([t for t in failed_tickers if t in tickers_to_fetch])
                }
            )

        except Exception as e:
            logger.error(f"yfinance batch download failed: {e}")
            # All tickers in this batch failed
            failed_tickers.extend([t for t in tickers_to_fetch if t not in prices])

    # Close Redis connection if we created it
    if own_redis and redis_client:
        try:
            await redis_client.close()
        except Exception:
            pass

    return prices, failed_tickers


# =============================================================================
# Get Portfolio Tool
# =============================================================================

async def get_portfolio_tool_handler(
    user_id: str,
    include_prices: bool = False
) -> Dict[str, Any]:
    """
    Get user's investment portfolio holdings from agentic-memories service.

    This tool provides structured data with a well-defined schema containing the user's
    stock positions, quantities, and purchase information. Use this to:
    - Answer questions about what stocks/assets the user owns
    - Calculate portfolio value, gains/losses, and performance metrics
    - Provide personalized investment insights based on their actual holdings
    - Compare their positions against market trends or news
    - Suggest rebalancing or diversification strategies
    - Any other questions about stocks or investments the user may have.
    - Use this tool in conjuction with other tools to get a comprehensive understanding of the user's investment situation.

    The holdings data includes ticker symbols, share quantities, purchase prices,
    and dates--everything needed to analyze their investment situation.

    When include_prices=True, enriches holdings with current market prices and
    calculates performance metrics (gain/loss, percentages, portfolio totals).

    Args:
        user_id: User identifier
        include_prices: If True, fetch current prices and calculate performance metrics.
                       Defaults to False for fast "what do I own?" queries.

    Returns:
        dict: Portfolio with holdings array (ticker, shares, cost_basis, purchase_date),
              total_holdings count, and last_updated timestamp.
              When include_prices=True, also includes current_price, current_value,
              gain_loss, gain_loss_pct per holding, plus portfolio totals.
    """
    start_time = time.time()

    # Get agentic-memories URL from config
    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    # Validate user_id
    if not user_id or not isinstance(user_id, str):
        logger.error(
            "Invalid user_id for portfolio retrieval",
            extra={"user_id": user_id, "error": "user_id must be non-empty string"}
        )
        return {
            "status": "error",
            "message": "Invalid user_id: must be non-empty string",
            "user_id": user_id
        }

    try:
        logger.info(
            "Retrieving portfolio via MCP tool",
            extra={
                "user_id": user_id,
                "include_prices": include_prices,
                "url": memories_url
            }
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{memories_url}/v1/portfolio",
                params={"user_id": user_id}
            )

            duration_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                result = response.json()
                holdings = result.get("holdings", [])

                logger.info(
                    "Portfolio retrieved successfully via MCP tool",
                    extra={
                        "user_id": user_id,
                        "holdings_count": len(holdings),
                        "include_prices": include_prices,
                        "duration_ms": duration_ms
                    }
                )

                # Build base response
                response_data = {
                    "status": "success",
                    "user_id": result.get("user_id", user_id),
                    "holdings": holdings,
                    "total_holdings": result.get("total_holdings", len(holdings)),
                    "last_updated": result.get("last_updated")
                }

                # Enrich with prices if requested
                if include_prices and holdings:
                    # Extract tickers from holdings
                    tickers = [h.get("ticker") for h in holdings if h.get("ticker")]

                    # Batch fetch prices with caching
                    prices, failed_tickers = await batch_fetch_prices_with_cache(tickers)

                    # Track totals for portfolio summary
                    total_value = 0.0
                    total_cost_basis = 0.0
                    price_fetch_errors = []

                    # Enrich each holding with price data
                    for holding in holdings:
                        ticker = holding.get("ticker")
                        if not ticker:
                            continue

                        shares = holding.get("shares", 0) or 0
                        avg_price = holding.get("avg_price", 0) or 0

                        if ticker in prices:
                            current_price = prices[ticker]
                            current_value = round(shares * current_price, 2)
                            cost_basis = round(shares * avg_price, 2)
                            gain_loss = round(current_value - cost_basis, 2)
                            gain_loss_pct = round((gain_loss / cost_basis) * 100, 2) if cost_basis > 0 else 0.0

                            holding["current_price"] = current_price
                            holding["current_value"] = current_value
                            holding["cost_basis"] = cost_basis
                            holding["gain_loss"] = gain_loss
                            holding["gain_loss_pct"] = gain_loss_pct

                            # Add to portfolio totals
                            total_value += current_value
                            total_cost_basis += cost_basis
                        else:
                            # Price fetch failed for this ticker
                            holding["current_price"] = None
                            holding["current_value"] = None
                            holding["cost_basis"] = round(shares * avg_price, 2) if avg_price else None
                            holding["gain_loss"] = None
                            holding["gain_loss_pct"] = None
                            if ticker in failed_tickers:
                                price_fetch_errors.append(ticker)

                    # Calculate portfolio totals
                    total_gain_loss = round(total_value - total_cost_basis, 2)
                    total_gain_loss_pct = round((total_gain_loss / total_cost_basis) * 100, 2) if total_cost_basis > 0 else 0.0

                    response_data["total_value"] = round(total_value, 2)
                    response_data["total_cost_basis"] = round(total_cost_basis, 2)
                    response_data["total_gain_loss"] = total_gain_loss
                    response_data["total_gain_loss_pct"] = total_gain_loss_pct
                    response_data["price_fetch_errors"] = price_fetch_errors
                    response_data["last_updated"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

                    logger.info(
                        "Portfolio enriched with prices",
                        extra={
                            "user_id": user_id,
                            "total_value": total_value,
                            "total_gain_loss_pct": total_gain_loss_pct,
                            "price_errors_count": len(price_fetch_errors)
                        }
                    )

                return response_data

            else:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("detail", error_msg)
                except Exception:
                    error_msg = response.text or error_msg

                logger.error(
                    "Portfolio retrieval failed via MCP tool",
                    extra={
                        "user_id": user_id,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "error",
                    "message": f"Failed to retrieve portfolio: {error_msg}",
                    "error_code": response.status_code,
                    "user_id": user_id
                }

    except httpx.TimeoutException as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Portfolio retrieval timed out via MCP tool",
            extra={
                "user_id": user_id,
                "error": str(e),
                "duration_ms": duration_ms
            }
        )
        return {
            "status": "error",
            "message": "Portfolio service timed out. Please try again.",
            "error_code": "TIMEOUT",
            "user_id": user_id
        }

    except (httpx.NetworkError, httpx.ConnectError) as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Network error retrieving portfolio via MCP tool",
            extra={
                "user_id": user_id,
                "error": str(e),
                "duration_ms": duration_ms
            }
        )
        return {
            "status": "error",
            "message": "Portfolio service unavailable. Please try again later.",
            "error_code": "NETWORK_ERROR",
            "user_id": user_id
        }

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Unexpected error retrieving portfolio via MCP tool",
            extra={
                "user_id": user_id,
                "error": str(e),
                "duration_ms": duration_ms
            },
            exc_info=True
        )
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}",
            "error_code": "INTERNAL_ERROR",
            "user_id": user_id
        }


# Get portfolio tool definition
get_portfolio_tool = {
    "name": "get_portfolio",
    "description": (
        "Get user's investment portfolio holdings. Returns structured data with "
        "ticker symbols, share counts, average purchase prices, and dates for all "
        "stocks, ETFs, and assets the user owns. Use this to: "
        "(1) Answer questions about what stocks/assets they own, "
        "(2) Calculate portfolio value, gains/losses, and performance metrics, "
        "(3) Provide personalized investment insights based on actual holdings, "
        "(4) Compare positions against market trends or news, "
        "(5) Suggest rebalancing or diversification strategies. "
        "Set include_prices=true when user asks 'how is my portfolio doing?' to get "
        "current prices, values, and gain/loss calculations. Use include_prices=false "
        "(default) for fast 'what do I own?' queries."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            },
            "include_prices": {
                "type": "boolean",
                "description": "If true, fetch current market prices and calculate performance metrics (current_value, gain_loss, gain_loss_pct). Adds ~1-2s latency. Default: false",
                "default": False
            }
        },
        "required": ["user_id"]
    },
    "handler": get_portfolio_tool_handler
}


# =============================================================================
# Add Holding Tool
# =============================================================================

async def add_holding_tool_handler(
    user_id: str,
    ticker: str,
    asset_name: str = None,
    shares: float = None,
    avg_price: float = None
) -> Dict[str, Any]:
    """
    Add or update a stock holding in user's portfolio.

    Uses UPSERT behavior: creates new holding if ticker doesn't exist,
    updates existing holding if it does.

    Args:
        user_id: User identifier
        ticker: Stock ticker symbol (e.g., 'AAPL', 'GOOGL')
        asset_name: Optional human-readable name (e.g., 'Apple Inc.')
        shares: Optional number of shares
        avg_price: Optional average purchase price per share

    Returns:
        dict: Result with holding details and created/updated flag
    """
    start_time = time.time()

    # Get agentic-memories URL from config
    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    # Validate user_id
    if not user_id or not isinstance(user_id, str):
        logger.error(
            "Invalid user_id for add_holding",
            extra={"user_id": user_id, "error": "user_id must be non-empty string"}
        )
        return {
            "status": "error",
            "message": "Invalid user_id: must be non-empty string"
        }

    # Normalize and validate ticker
    normalized_ticker = normalize_ticker(ticker)
    if normalized_ticker is None:
        logger.warning(
            "Invalid ticker format for add_holding",
            extra={"user_id": user_id, "ticker": ticker}
        )
        return {
            "status": "error",
            "message": f"Invalid ticker format: '{ticker}'. Ticker must be 1-10 alphanumeric characters (e.g., AAPL, GOOGL, BRK.B)."
        }

    # Build request payload
    payload = {
        "user_id": user_id,
        "ticker": normalized_ticker
    }
    if asset_name:
        payload["asset_name"] = asset_name
    if shares is not None:
        payload["shares"] = shares
    if avg_price is not None:
        payload["avg_price"] = avg_price

    try:
        logger.info(
            "Adding holding via MCP tool",
            extra={
                "user_id": user_id,
                "ticker": normalized_ticker,
                "shares": shares,
                "avg_price": avg_price
            }
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{memories_url}/v1/portfolio/holding",
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            duration_ms = int((time.time() - start_time) * 1000)

            if response.status_code in (200, 201):
                result = response.json()
                created = response.status_code == 201 or result.get("created", False)

                logger.info(
                    "Holding added/updated successfully via MCP tool",
                    extra={
                        "user_id": user_id,
                        "ticker": normalized_ticker,
                        "was_created": created,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "success",
                    "holding": {
                        "id": result.get("id"),
                        "ticker": result.get("ticker"),
                        "asset_name": result.get("asset_name"),
                        "shares": result.get("shares"),
                        "avg_price": result.get("avg_price"),
                        "first_acquired": result.get("first_acquired"),
                        "last_updated": result.get("last_updated")
                    },
                    "created": created,
                    "message": f"{'Added' if created else 'Updated'} {normalized_ticker} in your portfolio."
                }

            else:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("detail", error_msg)
                except Exception:
                    error_msg = response.text or error_msg

                logger.error(
                    "Add holding failed via MCP tool",
                    extra={
                        "user_id": user_id,
                        "ticker": normalized_ticker,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "error",
                    "message": f"Failed to add holding: {error_msg}",
                    "error_code": response.status_code
                }

    except httpx.TimeoutException as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Add holding timed out via MCP tool",
            extra={
                "user_id": user_id,
                "ticker": normalized_ticker,
                "error": str(e),
                "duration_ms": duration_ms
            }
        )
        return {
            "status": "error",
            "message": "Portfolio service timed out. Please try again.",
            "error_code": "TIMEOUT"
        }

    except (httpx.NetworkError, httpx.ConnectError) as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Network error adding holding via MCP tool",
            extra={
                "user_id": user_id,
                "ticker": normalized_ticker,
                "error": str(e),
                "duration_ms": duration_ms
            }
        )
        return {
            "status": "error",
            "message": "Portfolio service unavailable. Please try again later.",
            "error_code": "NETWORK_ERROR"
        }

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Unexpected error adding holding via MCP tool",
            extra={
                "user_id": user_id,
                "ticker": normalized_ticker,
                "error": str(e),
                "duration_ms": duration_ms
            },
            exc_info=True
        )
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}",
            "error_code": "INTERNAL_ERROR"
        }


# Add holding tool definition
add_holding_tool = {
    "name": "add_holding",
    "description": "Add or update a stock holding in user's portfolio. Use this tool when the user mentions buying stocks, adding to their portfolio, or wants to record a purchase. If the ticker already exists, it will update the existing holding (UPSERT behavior).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            },
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol (e.g., 'AAPL', 'GOOGL', 'BRK.B'). Will be normalized to uppercase."
            },
            "asset_name": {
                "type": "string",
                "description": "Optional human-readable name for the asset (e.g., 'Apple Inc.')"
            },
            "shares": {
                "type": "number",
                "description": "Number of shares owned"
            },
            "avg_price": {
                "type": "number",
                "description": "Average purchase price per share in USD"
            }
        },
        "required": ["user_id", "ticker"]
    },
    "handler": add_holding_tool_handler
}


# =============================================================================
# Update Holding Tool
# =============================================================================

async def update_holding_tool_handler(
    user_id: str,
    ticker: str,
    asset_name: str = None,
    shares: float = None,
    avg_price: float = None
) -> Dict[str, Any]:
    """
    Update an existing stock holding in user's portfolio.

    Unlike add_holding (which creates if not exists), this tool returns 404
    if the holding doesn't exist. Supports partial updates - only provided
    fields are updated.

    Args:
        user_id: User identifier
        ticker: Stock ticker symbol (e.g., 'AAPL', 'GOOGL')
        asset_name: Optional new asset name
        shares: Optional new number of shares
        avg_price: Optional new average purchase price

    Returns:
        dict: Updated holding details or error
    """
    start_time = time.time()

    # Get agentic-memories URL from config
    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    # Validate user_id
    if not user_id or not isinstance(user_id, str):
        return {
            "status": "error",
            "message": "Invalid user_id: must be non-empty string"
        }

    # Normalize and validate ticker
    normalized_ticker = normalize_ticker(ticker)
    if normalized_ticker is None:
        return {
            "status": "error",
            "message": f"Invalid ticker format: '{ticker}'. Ticker must be 1-10 alphanumeric characters."
        }

    # Build request payload (only include provided fields)
    payload = {"user_id": user_id}
    if asset_name is not None:
        payload["asset_name"] = asset_name
    if shares is not None:
        payload["shares"] = shares
    if avg_price is not None:
        payload["avg_price"] = avg_price

    try:
        logger.info(
            "Updating holding via MCP tool",
            extra={
                "user_id": user_id,
                "ticker": normalized_ticker,
                "updates": {k: v for k, v in payload.items() if k != "user_id"}
            }
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.put(
                f"{memories_url}/v1/portfolio/holding/{normalized_ticker}",
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            duration_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                result = response.json()

                logger.info(
                    "Holding updated successfully via MCP tool",
                    extra={
                        "user_id": user_id,
                        "ticker": normalized_ticker,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "success",
                    "ticker": result.get("ticker"),
                    "asset_name": result.get("asset_name"),
                    "shares": result.get("shares"),
                    "avg_price": result.get("avg_price"),
                    "first_acquired": result.get("first_acquired"),
                    "last_updated": result.get("last_updated"),
                    "message": f"Updated {normalized_ticker} in your portfolio."
                }

            elif response.status_code == 404:
                logger.info(
                    "Holding not found for update",
                    extra={
                        "user_id": user_id,
                        "ticker": normalized_ticker,
                        "duration_ms": duration_ms
                    }
                )
                return {
                    "status": "error",
                    "message": f"Holding not found: You don't have {normalized_ticker} in your portfolio.",
                    "error_code": 404
                }

            else:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("detail", error_msg)
                except Exception:
                    error_msg = response.text or error_msg

                logger.error(
                    "Update holding failed via MCP tool",
                    extra={
                        "user_id": user_id,
                        "ticker": normalized_ticker,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "error",
                    "message": f"Failed to update holding: {error_msg}",
                    "error_code": response.status_code
                }

    except httpx.TimeoutException:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Update holding timed out", extra={"user_id": user_id, "ticker": normalized_ticker, "duration_ms": duration_ms})
        return {"status": "error", "message": "Portfolio service timed out. Please try again.", "error_code": "TIMEOUT"}

    except (httpx.NetworkError, httpx.ConnectError) as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Network error updating holding", extra={"user_id": user_id, "ticker": normalized_ticker, "error": str(e), "duration_ms": duration_ms})
        return {"status": "error", "message": "Portfolio service unavailable. Please try again later.", "error_code": "NETWORK_ERROR"}

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Unexpected error updating holding", extra={"user_id": user_id, "ticker": normalized_ticker, "error": str(e), "duration_ms": duration_ms}, exc_info=True)
        return {"status": "error", "message": f"Unexpected error: {str(e)}", "error_code": "INTERNAL_ERROR"}


# Update holding tool definition
update_holding_tool = {
    "name": "update_holding",
    "description": "Update an existing stock holding in user's portfolio. Use this when the user wants to change the number of shares or average price of a stock they already own. Returns error if the holding doesn't exist (use add_holding to create new holdings).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            },
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol to update (e.g., 'AAPL')"
            },
            "asset_name": {
                "type": "string",
                "description": "Optional new human-readable name for the asset"
            },
            "shares": {
                "type": "number",
                "description": "New number of shares owned"
            },
            "avg_price": {
                "type": "number",
                "description": "New average purchase price per share in USD"
            }
        },
        "required": ["user_id", "ticker"]
    },
    "handler": update_holding_tool_handler
}


# =============================================================================
# Remove Holding Tool
# =============================================================================

async def remove_holding_tool_handler(
    user_id: str,
    ticker: str
) -> Dict[str, Any]:
    """
    Remove a stock holding from user's portfolio.

    Deletes the holding identified by user_id + ticker.
    Returns 404 if holding doesn't exist.

    Args:
        user_id: User identifier
        ticker: Stock ticker symbol to remove (e.g., 'AAPL')

    Returns:
        dict: Confirmation of deletion or error
    """
    start_time = time.time()

    # Get agentic-memories URL from config
    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    # Validate user_id
    if not user_id or not isinstance(user_id, str):
        return {
            "status": "error",
            "message": "Invalid user_id: must be non-empty string"
        }

    # Normalize and validate ticker
    normalized_ticker = normalize_ticker(ticker)
    if normalized_ticker is None:
        return {
            "status": "error",
            "message": f"Invalid ticker format: '{ticker}'. Ticker must be 1-10 alphanumeric characters."
        }

    try:
        logger.info(
            "Removing holding via MCP tool",
            extra={
                "user_id": user_id,
                "ticker": normalized_ticker
            }
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.delete(
                f"{memories_url}/v1/portfolio/holding/{normalized_ticker}",
                params={"user_id": user_id}
            )

            duration_ms = int((time.time() - start_time) * 1000)

            # 200 = OK with response body, 204 = No Content (success with no body)
            if response.status_code in (200, 204):
                ticker_name = normalized_ticker
                if response.status_code == 200:
                    try:
                        result = response.json()
                        ticker_name = result.get("ticker", normalized_ticker)
                    except Exception:
                        pass

                logger.info(
                    "Holding removed successfully via MCP tool",
                    extra={
                        "user_id": user_id,
                        "ticker": normalized_ticker,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "success",
                    "deleted": True,
                    "ticker": ticker_name,
                    "message": f"Removed {normalized_ticker} from your portfolio."
                }

            elif response.status_code == 404:
                logger.info(
                    "Holding not found for removal",
                    extra={
                        "user_id": user_id,
                        "ticker": normalized_ticker,
                        "duration_ms": duration_ms
                    }
                )
                return {
                    "status": "error",
                    "message": f"Holding not found: You don't have {normalized_ticker} in your portfolio.",
                    "error_code": 404
                }

            else:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("detail", error_msg)
                except Exception:
                    error_msg = response.text or error_msg

                logger.error(
                    "Remove holding failed via MCP tool",
                    extra={
                        "user_id": user_id,
                        "ticker": normalized_ticker,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "error",
                    "message": f"Failed to remove holding: {error_msg}",
                    "error_code": response.status_code
                }

    except httpx.TimeoutException:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Remove holding timed out", extra={"user_id": user_id, "ticker": normalized_ticker, "duration_ms": duration_ms})
        return {"status": "error", "message": "Portfolio service timed out. Please try again.", "error_code": "TIMEOUT"}

    except (httpx.NetworkError, httpx.ConnectError) as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Network error removing holding", extra={"user_id": user_id, "ticker": normalized_ticker, "error": str(e), "duration_ms": duration_ms})
        return {"status": "error", "message": "Portfolio service unavailable. Please try again later.", "error_code": "NETWORK_ERROR"}

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Unexpected error removing holding", extra={"user_id": user_id, "ticker": normalized_ticker, "error": str(e), "duration_ms": duration_ms}, exc_info=True)
        return {"status": "error", "message": f"Unexpected error: {str(e)}", "error_code": "INTERNAL_ERROR"}


# Remove holding tool definition
remove_holding_tool = {
    "name": "remove_holding",
    "description": "Remove a stock holding from user's portfolio. Use this when the user has sold all shares of a stock and wants it removed from their portfolio. Returns error if the holding doesn't exist.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            },
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol to remove (e.g., 'AAPL')"
            }
        },
        "required": ["user_id", "ticker"]
    },
    "handler": remove_holding_tool_handler
}


# =============================================================================
# Clear Portfolio Tool
# =============================================================================

async def clear_portfolio_tool_handler(
    user_id: str,
    confirmation: str = None
) -> Dict[str, Any]:
    """
    Clear ALL holdings from user's portfolio.

    WARNING: This is a destructive operation that removes ALL holdings.
    Requires confirmation parameter set to 'DELETE_ALL' for safety.

    Args:
        user_id: User identifier
        confirmation: Must be exactly 'DELETE_ALL' to proceed

    Returns:
        dict: Count of deleted holdings or error
    """
    start_time = time.time()

    # Get agentic-memories URL from config
    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    # Validate user_id
    if not user_id or not isinstance(user_id, str):
        return {
            "status": "error",
            "message": "Invalid user_id: must be non-empty string"
        }

    # Validate confirmation
    if confirmation != "DELETE_ALL":
        logger.warning(
            "Clear portfolio called without proper confirmation",
            extra={"user_id": user_id, "confirmation": confirmation}
        )
        return {
            "status": "error",
            "message": "Confirmation required. This will delete ALL holdings in the portfolio. Set confirmation='DELETE_ALL' to proceed.",
            "error_code": "CONFIRMATION_REQUIRED"
        }

    try:
        logger.info(
            "Clearing portfolio via MCP tool",
            extra={"user_id": user_id}
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.delete(
                f"{memories_url}/v1/portfolio",
                params={"user_id": user_id, "confirmation": "DELETE_ALL"}
            )

            duration_ms = int((time.time() - start_time) * 1000)

            # 200 = OK with response body, 204 = No Content (success with no body)
            if response.status_code in (200, 204):
                holdings_removed = 0
                if response.status_code == 200:
                    try:
                        result = response.json()
                        holdings_removed = result.get("holdings_removed", 0)
                    except Exception:
                        pass

                logger.info(
                    "Portfolio cleared successfully via MCP tool",
                    extra={
                        "user_id": user_id,
                        "holdings_removed": holdings_removed,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "success",
                    "deleted": True,
                    "holdings_removed": holdings_removed,
                    "message": f"Cleared your entire portfolio. {holdings_removed} holding{'s' if holdings_removed != 1 else ''} removed."
                }

            else:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("detail", error_msg)
                except Exception:
                    error_msg = response.text or error_msg

                logger.error(
                    "Clear portfolio failed via MCP tool",
                    extra={
                        "user_id": user_id,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "error",
                    "message": f"Failed to clear portfolio: {error_msg}",
                    "error_code": response.status_code
                }

    except httpx.TimeoutException:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Clear portfolio timed out", extra={"user_id": user_id, "duration_ms": duration_ms})
        return {"status": "error", "message": "Portfolio service timed out. Please try again.", "error_code": "TIMEOUT"}

    except (httpx.NetworkError, httpx.ConnectError) as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Network error clearing portfolio", extra={"user_id": user_id, "error": str(e), "duration_ms": duration_ms})
        return {"status": "error", "message": "Portfolio service unavailable. Please try again later.", "error_code": "NETWORK_ERROR"}

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Unexpected error clearing portfolio", extra={"user_id": user_id, "error": str(e), "duration_ms": duration_ms}, exc_info=True)
        return {"status": "error", "message": f"Unexpected error: {str(e)}", "error_code": "INTERNAL_ERROR"}


# Clear portfolio tool definition
clear_portfolio_tool = {
    "name": "clear_portfolio",
    "description": "DANGER: Clear ALL holdings from user's portfolio. This permanently deletes every stock in the portfolio. Only use when the user explicitly confirms they want to remove everything. Requires confirmation='DELETE_ALL' parameter.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            },
            "confirmation": {
                "type": "string",
                "description": "Must be exactly 'DELETE_ALL' to confirm this destructive operation",
                "enum": ["DELETE_ALL"]
            }
        },
        "required": ["user_id", "confirmation"]
    },
    "handler": clear_portfolio_tool_handler
}


# =============================================================================
# Exports
# =============================================================================

# All tool definitions for easy registration
PORTFOLIO_TOOLS = [
    get_portfolio_tool,
    add_holding_tool,
    update_holding_tool,
    remove_holding_tool,
    clear_portfolio_tool,
]

# Utility exports
__all__ = [
    # Constants
    "PRICE_CACHE_TTL",
    "TICKER_PATTERN",
    # Utility functions
    "normalize_ticker",
    "batch_fetch_prices_with_cache",
    # Tool handlers
    "get_portfolio_tool_handler",
    "add_holding_tool_handler",
    "update_holding_tool_handler",
    "remove_holding_tool_handler",
    "clear_portfolio_tool_handler",
    # Tool definitions
    "get_portfolio_tool",
    "add_holding_tool",
    "update_holding_tool",
    "remove_holding_tool",
    "clear_portfolio_tool",
    # Convenience list
    "PORTFOLIO_TOOLS",
]
