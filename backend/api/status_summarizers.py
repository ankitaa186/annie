"""
Status Summarizers for MCP Tool Results

Provides concise, user-friendly summaries of tool execution results for real-time
status updates. Each summarizer extracts key information from tool results and
formats it into a brief (<50 chars when possible) summary string.

Used by mcp_client.py to generate status messages after tool execution completes.
"""
from typing import Dict, Any, Optional


def summarize_portfolio_result(result: Dict[str, Any]) -> str:
    """Summarize get_portfolio tool result.

    Result shape:
        {
            "status": "success",
            "holdings": [...],
            "total_holdings": 3,
            "total_value": 15420.50,  # Only when include_prices=True
            "total_gain_loss_pct": 12.5  # Only when include_prices=True
        }

    Args:
        result: Tool result dictionary

    Returns:
        Concise summary string

    Examples:
        "3 holdings, $15,420 value" (with prices)
        "3 holdings" (without prices)
    """
    if result.get("status") == "error":
        return result.get("message", "Failed")[:50]

    holdings_count = result.get("total_holdings", 0)

    # Check if prices were included
    if "total_value" in result:
        total_value = result.get("total_value", 0)
        return f"{holdings_count} holdings, ${total_value:,.0f} value"
    else:
        return f"{holdings_count} holdings"


def summarize_add_holding_result(result: Dict[str, Any]) -> str:
    """Summarize add_holding tool result.

    Result shape:
        {
            "status": "success",
            "holding": {"ticker": "AAPL", "shares": 10, ...},
            "created": true,
            "message": "Added AAPL in your portfolio."
        }

    Args:
        result: Tool result dictionary

    Returns:
        Concise summary string

    Examples:
        "Added AAPL: 10 shares"
        "Updated AAPL: 10 shares"
    """
    if result.get("status") == "error":
        return result.get("message", "Failed")[:50]

    holding = result.get("holding", {})
    ticker = holding.get("ticker", "???")
    shares = holding.get("shares", 0)
    created = result.get("created", False)

    action = "Added" if created else "Updated"
    return f"{action} {ticker}: {shares} shares"


def summarize_update_holding_result(result: Dict[str, Any]) -> str:
    """Summarize update_holding tool result.

    Result shape:
        {
            "status": "success",
            "ticker": "AAPL",
            "shares": 15,
            "message": "Updated AAPL in your portfolio."
        }

    Args:
        result: Tool result dictionary

    Returns:
        Concise summary string

    Examples:
        "Updated AAPL"
    """
    if result.get("status") == "error":
        return result.get("message", "Failed")[:50]

    ticker = result.get("ticker", "???")
    return f"Updated {ticker}"


def summarize_remove_holding_result(result: Dict[str, Any]) -> str:
    """Summarize remove_holding tool result.

    Result shape:
        {
            "status": "success",
            "deleted": true,
            "ticker": "AAPL",
            "message": "Removed AAPL from your portfolio."
        }

    Args:
        result: Tool result dictionary

    Returns:
        Concise summary string

    Examples:
        "Removed AAPL"
    """
    if result.get("status") == "error":
        return result.get("message", "Failed")[:50]

    ticker = result.get("ticker", "???")
    return f"Removed {ticker}"


def summarize_clear_portfolio_result(result: Dict[str, Any]) -> str:
    """Summarize clear_portfolio tool result.

    Result shape:
        {
            "status": "success",
            "deleted": true,
            "holdings_removed": 3,
            "message": "Cleared your entire portfolio. 3 holdings removed."
        }

    Args:
        result: Tool result dictionary

    Returns:
        Concise summary string

    Examples:
        "Portfolio cleared (3 removed)"
    """
    if result.get("status") == "error":
        return result.get("message", "Failed")[:50]

    holdings_removed = result.get("holdings_removed", 0)
    return f"Portfolio cleared ({holdings_removed} removed)"


def summarize_analyze_stock_result(result: Dict[str, Any]) -> str:
    """Summarize analyze_stock tool result.

    Result shape:
        {
            "status": "success",
            "ticker": "AAPL",
            "current_price": 175.50,
            "change_1d_pct": 2.3,
            "name": "Apple Inc."
        }

    Args:
        result: Tool result dictionary

    Returns:
        Concise summary string

    Examples:
        "AAPL $175.50 (+2.3%)"
        "AAPL $175.50 (-1.5%)"
    """
    if result.get("status") == "error":
        return result.get("message", "Failed")[:50]

    ticker = result.get("ticker") or "???"
    price = result.get("current_price") or 0
    change = result.get("change_1d_pct") or 0
    sign = "+" if change >= 0 else ""
    return f"{ticker} ${price:.2f} ({sign}{change:.1f}%)"


def summarize_stock_history_result(result: Dict[str, Any]) -> str:
    """Summarize get_stock_history tool result.

    Result shape:
        {
            "status": "success",
            "ticker": "AAPL",
            "period": "1mo",
            "data_points": 22
        }

    Args:
        result: Tool result dictionary

    Returns:
        Concise summary string

    Examples:
        "History loaded: 1mo (22 days)"
    """
    if result.get("status") == "error":
        return result.get("message", "Failed")[:50]

    period = result.get("period", "???")
    data_points = result.get("data_points", 0)
    return f"History loaded: {period} ({data_points} days)"


def summarize_profile_result(result: Dict[str, Any]) -> str:
    """Summarize get_user_profile tool result.

    Result shape:
        {
            "status": "success",
            "user_id": "123456",
            "completeness": 67
        }

    Args:
        result: Tool result dictionary

    Returns:
        Concise summary string

    Examples:
        "Profile loaded (67% complete)"
    """
    if result.get("status") == "error":
        return result.get("error", "Failed")[:50]

    completeness = result.get("completeness", 0)
    return f"Profile loaded ({completeness}% complete)"


def summarize_store_memory_result(result: Dict[str, Any]) -> str:
    """Summarize store_memory tool result.

    Result shape:
        {
            "status": "success",
            "memories_created": 2,
            "memory_ids": ["mem_abc", "mem_def"]
        }

    Args:
        result: Tool result dictionary

    Returns:
        Concise summary string

    Examples:
        "Memory saved (2 items)"
        "Memory saved"
    """
    if result.get("status") == "error":
        return result.get("message", "Failed")[:50]

    memories_created = result.get("memories_created", 0)
    if memories_created > 1:
        return f"Memory saved ({memories_created} items)"
    else:
        return "Memory saved"


def summarize_retrieve_memories_result(result: Dict[str, Any]) -> str:
    """Summarize retrieve_memories tool result.

    Result shape:
        {
            "status": "success",
            "memory_count": 5,
            "memories": [...]
        }

    Args:
        result: Tool result dictionary

    Returns:
        Concise summary string

    Examples:
        "Found 5 memories"
        "No memories found"
    """
    if result.get("status") == "error":
        return result.get("message", "Failed")[:50]

    memory_count = result.get("memory_count", 0)
    if memory_count == 0:
        return "No memories found"
    elif memory_count == 1:
        return "Found 1 memory"
    else:
        return f"Found {memory_count} memories"


def summarize_internet_search_result(result: Dict[str, Any]) -> str:
    """Summarize internet_search tool result (placeholder for future MCP-based search).

    Result shape (expected):
        {
            "status": "success",
            "results": [...]
        }

    Args:
        result: Tool result dictionary

    Returns:
        Concise summary string

    Examples:
        "Found 5 results"
        "No results found"
    """
    if result.get("status") == "error":
        return result.get("message", "Failed")[:50]

    results = result.get("results", [])
    count = len(results)
    if count == 0:
        return "No results found"
    elif count == 1:
        return "Found 1 result"
    else:
        return f"Found {count} results"


def summarize_health_check_result(result: Dict[str, Any]) -> str:
    """Summarize health_check tool result.

    Result shape:
        {
            "status": "ok",
            "timestamp": "2025-12-16T12:00:00Z"
        }

    Args:
        result: Tool result dictionary

    Returns:
        Concise summary string

    Examples:
        "Health check OK"
    """
    status = result.get("status", "unknown")
    if status == "ok":
        return "Health check OK"
    else:
        return f"Health check: {status}"


# Registry mapping tool names to their summarizer functions
SUMMARIZERS = {
    "get_portfolio": summarize_portfolio_result,
    "add_holding": summarize_add_holding_result,
    "update_holding": summarize_update_holding_result,
    "remove_holding": summarize_remove_holding_result,
    "clear_portfolio": summarize_clear_portfolio_result,
    "analyze_stock": summarize_analyze_stock_result,
    "get_stock_history": summarize_stock_history_result,
    "get_user_profile": summarize_profile_result,
    "store_memory": summarize_store_memory_result,
    "retrieve_memories": summarize_retrieve_memories_result,
    "internet_search": summarize_internet_search_result,
    "health_check": summarize_health_check_result,
}


def summarize_tool_result(tool_name: str, result: Dict[str, Any]) -> str:
    """
    Summarize tool result for status display.

    Main entry point for tool result summarization. Looks up the appropriate
    summarizer for the tool and generates a concise summary. Falls back to
    generic summary if tool not recognized or summarizer fails.

    Args:
        tool_name: Name of the tool that was executed
        result: Tool result dictionary

    Returns:
        Concise summary string (<50 chars when possible) or "Complete" as fallback

    Examples:
        summarize_tool_result("get_portfolio", {...}) -> "3 holdings, $15,420 value"
        summarize_tool_result("analyze_stock", {...}) -> "AAPL $175.50 (+2.3%)"
        summarize_tool_result("unknown_tool", {...}) -> "Complete"
    """
    # Look up tool-specific summarizer
    summarizer = SUMMARIZERS.get(tool_name)

    if summarizer:
        try:
            return summarizer(result)
        except Exception as e:
            # Log error but fall through to generic summary
            from api.logging import get_logger
            logger = get_logger(__name__)
            logger.warning(
                "Summarizer failed, using generic summary",
                extra={
                    "tool_name": tool_name,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )

    # Generic fallback for unknown tools or summarizer failures
    if result.get("status") == "error":
        error_message = result.get("message", "Failed")
        # Truncate to 50 chars
        return error_message[:50]

    return "Complete"
