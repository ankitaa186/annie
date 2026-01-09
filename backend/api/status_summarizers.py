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
        return result.get("message", "Failed")[:500]

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
        return result.get("message", "Failed")[:500]

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
        return result.get("message", "Failed")[:500]

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
        return result.get("message", "Failed")[:500]

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
        return result.get("message", "Failed")[:500]

    holdings_removed = result.get("holdings_removed", 0)
    return f"Portfolio cleared ({holdings_removed} removed)"


def summarize_get_stock_data_result(result: Dict[str, Any]) -> str:
    """Summarize get_stock_data tool result.

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
        return result.get("message", "Failed")[:500]

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
        return result.get("message", "Failed")[:500]

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
        return result.get("error", "Failed")[:500]

    completeness = result.get("completeness", 0)
    return f"Profile loaded ({completeness}% complete)"


def summarize_store_memory_result(result: Dict[str, Any]) -> str:
    """Summarize store_memory tool result.

    Result shape (updated for Story 14.5):
        {
            "status": "success"|"error",
            "memory_id": str,              # UUID of stored memory
            "message": str,
            "storage": {
                "chromadb": bool,          # Always true on success
                "episodic": bool,          # True if event_timestamp provided
                "emotional": bool,         # True if emotional_state provided
                "procedural": bool         # True if skill_name provided
            }
        }

    Also handles legacy format:
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
        "Memory saved (abc123def4...)"
        "Memory saved (2 items)"
        "Memory saved"
    """
    if result.get("status") == "error":
        return result.get("message", "Failed")[:500]

    # New format with memory_id (Story 14.5)
    memory_id = result.get("memory_id")
    if memory_id:
        # Show truncated memory_id (first 12 chars)
        truncated_id = memory_id[:12] if len(memory_id) > 12 else memory_id
        return f"Memory saved ({truncated_id}...)"

    # Legacy format with memories_created
    memories_created = result.get("memories_created", 0)
    if memories_created > 1:
        return f"Memory saved ({memories_created} items)"
    else:
        return "Memory saved"


def summarize_delete_memory_result(result: Dict[str, Any]) -> str:
    """Summarize delete_memory tool result (Story 14.5).

    Result shape:
        {
            "status": "success"|"error",
            "deleted": bool,
            "memory_id": str,
            "message": str,
            "storage": {
                "chromadb": bool,
                "episodic": bool,
                "emotional": bool,
                "procedural": bool
            }
        }

    Args:
        result: Tool result dictionary

    Returns:
        Concise summary string

    Examples:
        "Memory deleted"
        "Delete failed: Memory not found"
        "Delete failed: Unauthorized"
    """
    if result.get("status") == "error" or not result.get("deleted", False):
        message = result.get("message", "Failed")
        return f"Delete failed: {message}"[:500]

    return "Memory deleted"


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
        return result.get("message", "Failed")[:500]

    memory_count = result.get("memory_count", 0)
    if memory_count == 0:
        return "No memories found"
    elif memory_count == 1:
        return "Found 1 memory"
    else:
        return f"Found {memory_count} memories"


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


def summarize_web_search_result(result: Dict[str, Any]) -> str:
    """Summarize web_search tool result.

    Result shape:
        {
            "status": "success" | "error",
            "provider": "tavily" | "duckduckgo",
            "results": [...],
            "query": "...",
            "error_message": "..."  # Only on error
        }

    Args:
        result: Tool result dictionary

    Returns:
        Concise summary string

    Examples:
        "Found 5 results"
        "No results found"
        "Search failed: rate limit"
    """
    if result.get("status") == "error":
        error_msg = result.get("error_message", "Failed")
        return f"Search failed: {error_msg}"[:200]

    results = result.get("results", [])
    count = len(results)

    if count == 0:
        return "No results found"
    elif count == 1:
        return "Found 1 result"
    else:
        return f"Found {count} results"


def summarize_update_user_profile_result(result: Dict[str, Any]) -> str:
    """Summarize update_user_profile tool result (Story 15.4).

    Result shape:
        {
            "status": "success"|"error",
            "user_id": str,
            "category": str,
            "field_name": str,
            "value": any,
            "previous_value": any,
            "confidence": 100.0,
            "last_updated": str,
            "error_message": str  # On error
        }

    Args:
        result: Tool result dictionary

    Returns:
        Concise summary string

    Examples:
        "Updated preferences/communication_style"
        "Profile update failed: Field not found"
    """
    if result.get("status") == "error":
        error_msg = result.get("error_message", "Failed")
        return f"Profile update failed: {error_msg}"[:200]

    field_name = result.get("field_name", "profile")
    category = result.get("category", "")

    # Show field with category context if available
    if category:
        return f"Updated {category}/{field_name}"
    return f"Updated {field_name}"


def summarize_web_crawl_result(result: Dict[str, Any]) -> str:
    """Summarize web_crawl tool result.

    Result shape:
        {
            "status": "success"|"error",
            "provider": "crawl4ai"|"jina",
            "url": str,
            "title": str,
            "content": str,
            "metadata": {...},
            "truncated": bool,
            "error_message": str (on error)
        }

    Args:
        result: Tool result dictionary

    Returns:
        Concise summary string (<50 chars when possible)

    Examples:
        "Page loaded (Understanding React...)"
        "Page loaded"
        "Failed: Timeout"
    """
    if result.get("status") == "error":
        error_msg = result.get("error_message", "Failed")
        # Truncate long error messages
        if len(error_msg) > 40:
            error_msg = error_msg[:37] + "..."
        return f"Failed: {error_msg}"

    title = result.get("title", "")
    if title:
        # Truncate title to fit in 50 char limit
        if len(title) > 30:
            title = title[:27] + "..."
        return f"Page loaded ({title})"

    return "Page loaded"


def summarize_reddit_search_result(result: Dict[str, Any]) -> str:
    """Summarize reddit_search tool result.

    Result shape:
        {
            "status": "success",
            "provider": "praw" | "json_api",
            "query": "search query",
            "subreddit": "python" | "all",
            "results": [...]
        }

    Args:
        result: Tool result dictionary

    Returns:
        Concise summary string

    Examples:
        "Found 5 posts"
        "Found 3 posts in r/python"
        "No posts found"
        "Reddit search failed"
    """
    if result.get("status") == "error":
        error_message = result.get("error_message", "Failed")
        return f"Reddit search failed: {error_message}"[:200]

    results = result.get("results", [])
    count = len(results)
    subreddit = result.get("subreddit", "all")

    if count == 0:
        return "No posts found"
    elif subreddit and subreddit != "all":
        return f"Found {count} post{'s' if count != 1 else ''} in r/{subreddit}"
    else:
        return f"Found {count} post{'s' if count != 1 else ''}"


def summarize_compact_memories_result(result: Dict[str, Any]) -> str:
    """Summarize compact_memories tool result.

    Result shape:
        {
            "status": "success"|"error",
            "message": str,
            "stats": {
                "ttl_deleted": int,
                "consolidated_count": int,
                "sources_removed": int,
                "applied_upserts": int,
                "applied_deletes": int,
                "duration_ms": int
            }
        }
    """
    if result.get("status") == "error":
        return result.get("message", "Failed")[:200]

    stats = result.get("stats", {})
    consolidated = stats.get("consolidated_count", 0)
    deleted = stats.get("ttl_deleted", 0) + stats.get("sources_removed", 0)

    if consolidated > 0 and deleted > 0:
        return f"Compacted: {consolidated} merged, {deleted} removed"
    elif consolidated > 0:
        return f"Compacted: {consolidated} memories merged"
    elif deleted > 0:
        return f"Compacted: {deleted} memories removed"
    else:
        return "Compaction complete (no changes)"


def summarize_create_trigger_result(result: Dict[str, Any]) -> str:
    """Summarize create_trigger tool result.

    Result shape:
        {
            "status": "success"|"error",
            "trigger": {...},
            "message": str
        }
    """
    if result.get("status") == "error":
        return result.get("message", "Failed")[:200]

    trigger = result.get("trigger", {})
    intent_name = trigger.get("intent_name", "trigger")
    return f"Created: {intent_name}"


def summarize_list_triggers_result(result: Dict[str, Any]) -> str:
    """Summarize list_triggers tool result."""
    if result.get("status") == "error":
        return result.get("message", "Failed")[:200]

    count = result.get("trigger_count", 0)
    if count == 0:
        return "No triggers found"
    return f"Found {count} trigger{'s' if count != 1 else ''}"


def summarize_update_trigger_result(result: Dict[str, Any]) -> str:
    """Summarize update_trigger tool result."""
    if result.get("status") == "error":
        return result.get("message", "Failed")[:200]

    trigger = result.get("trigger", {})
    intent_name = trigger.get("intent_name", "trigger")
    return f"Updated: {intent_name}"


def summarize_delete_trigger_result(result: Dict[str, Any]) -> str:
    """Summarize delete_trigger tool result."""
    if result.get("status") == "error":
        return result.get("message", "Failed")[:200]

    return "Trigger deleted"


# Registry mapping tool names to their summarizer functions
SUMMARIZERS = {
    "get_portfolio": summarize_portfolio_result,
    "add_holding": summarize_add_holding_result,
    "update_holding": summarize_update_holding_result,
    "remove_holding": summarize_remove_holding_result,
    "clear_portfolio": summarize_clear_portfolio_result,
    "get_stock_data": summarize_get_stock_data_result,
    "get_stock_history": summarize_stock_history_result,
    "get_user_profile": summarize_profile_result,
    "store_memory": summarize_store_memory_result,
    "delete_memory": summarize_delete_memory_result,  # Story 14.5
    "retrieve_memories": summarize_retrieve_memories_result,
    "compact_memories": summarize_compact_memories_result,  # Story 14.5
    "health_check": summarize_health_check_result,
    "update_user_profile": summarize_update_user_profile_result,  # Story 15.4
    "web_search": summarize_web_search_result,  # Story 15.1
    "reddit_search": summarize_reddit_search_result,  # Story 15.3
    "web_crawl": summarize_web_crawl_result,  # Story 15.2
    "create_trigger": summarize_create_trigger_result,  # Epic 13
    "list_triggers": summarize_list_triggers_result,  # Epic 13
    "update_trigger": summarize_update_trigger_result,  # Epic 13
    "delete_trigger": summarize_delete_trigger_result,  # Epic 13
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
        summarize_tool_result("get_stock_data", {...}) -> "AAPL $175.50 (+2.3%)"
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
        # Truncate to 500 chars to show full error context
        return error_message[:500]

    return "Complete"
