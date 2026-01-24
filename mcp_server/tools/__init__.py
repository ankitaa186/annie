"""
MCP Tools Package

This package contains modularized tool implementations for the MCP server.
Each module focuses on a specific domain (memory, profile, portfolio, etc.).

Usage:
    from mcp_server.tools import (
        ToolRegistry,
        health_check_tool,
        store_memory_tool,
        # ... other tools
    )
"""

# Registry
from .registry import ToolRegistry

# Memory Tools (Epic 3, 12, 14)
from .memory import (
    health_check_tool,
    health_check_tool_handler,
    store_memory_tool,
    store_memory_tool_handler,
    delete_memory_tool,
    delete_memory_tool_handler,
    retrieve_memories_tool,
    retrieve_memories_tool_handler,
    compact_memories_tool,
    compact_memories_tool_handler,
)

# Profile Tools (Epic 7, 15.4)
from .profile import (
    get_user_profile_tool,
    get_user_profile_tool_handler,
    update_user_profile_tool,
    update_user_profile_tool_handler,
    ALLOWED_PROFILE_CATEGORIES,
    CANONICAL_FIELDS,
    FIELD_NAME_ALIASES,
)

# Portfolio Tools (Epic 10)
from .portfolio import (
    normalize_ticker,
    batch_fetch_prices_with_cache,
    get_portfolio_tool,
    get_portfolio_tool_handler,
    add_holding_tool,
    add_holding_tool_handler,
    update_holding_tool,
    update_holding_tool_handler,
    remove_holding_tool,
    remove_holding_tool_handler,
    clear_portfolio_tool,
    clear_portfolio_tool_handler,
    PRICE_CACHE_TTL,
    TICKER_PATTERN,
)

# Stock Analysis Tools (Epic 10 - Story 10.6)
from .stock_analysis import (
    calculate_rsi,
    format_market_cap,
    determine_trend,
    get_stock_data_tool,
    get_stock_data_tool_handler,
    get_stock_history_tool,
    get_stock_history_tool_handler,
    get_financials_tool,
    get_financials_tool_handler,
    FINANCIALS_CACHE_TTL,
)

# SEC Edgar Tools (10-K, 10-Q, 8-K filings)
from .sec_edgar import (
    get_sec_filings_tool,
    get_sec_filings_tool_handler,
    SEC_FILINGS_CACHE_TTL,
)

# Trigger/Proactive Tools (Epic 13)
from .triggers import (
    create_trigger_tool,
    create_trigger_tool_handler,
    list_triggers_tool,
    list_triggers_tool_handler,
    update_trigger_tool,
    update_trigger_tool_handler,
    delete_trigger_tool,
    delete_trigger_tool_handler,
)

# Web Search Tools (Epic 15 - Story 15.1)
from .web_search import (
    web_search_tool,
    web_search_tool_handler,
    _tavily_search,
    _duckduckgo_search,
)

# Web Crawl Tools (Epic 15 - Story 15.2)
from .web_crawl import (
    web_crawl_tool,
    web_crawl_tool_handler,
    _is_valid_url,
    _crawl4ai_fetch,
    _jina_reader_fetch,
)

# Reddit Search Tools (Epic 15 - Story 15.3)
from .reddit_search import (
    reddit_search_tool,
    reddit_search_tool_handler,
    _praw_search_sync,
    _reddit_json_search,
)

# Home Assistant Tools (Epic 16 - Stories 16.1, 16.2, 16.6)
from .home_assistant import (
    home_assistant_query_tool,
    home_assistant_query_handler,
    home_assistant_control_tool,
    home_assistant_control_handler,
    send_voice_message_to_smart_home_tool,
    send_voice_message_to_smart_home_handler,
    HomeAssistantClient,
    AllowlistValidator,
    get_allowlist_validator,
    reset_allowlist_validator,
    reset_voice_message_cooldown,
    _set_voice_cooldown,
    _get_redis_client,
    VOICE_COOLDOWN_REDIS_KEY,
    map_action_to_service,
    build_ssml_message,
    get_voice_delivery_method,
    VOICE_TYPES,
    VOICE_MESSAGE_COOLDOWN_SECONDS,
)

__all__ = [
    # Registry
    "ToolRegistry",

    # Memory
    "health_check_tool",
    "health_check_tool_handler",
    "store_memory_tool",
    "store_memory_tool_handler",
    "delete_memory_tool",
    "delete_memory_tool_handler",
    "retrieve_memories_tool",
    "retrieve_memories_tool_handler",
    "compact_memories_tool",
    "compact_memories_tool_handler",

    # Profile
    "get_user_profile_tool",
    "get_user_profile_tool_handler",
    "update_user_profile_tool",
    "update_user_profile_tool_handler",
    "ALLOWED_PROFILE_CATEGORIES",
    "CANONICAL_FIELDS",
    "FIELD_NAME_ALIASES",

    # Portfolio
    "normalize_ticker",
    "batch_fetch_prices_with_cache",
    "get_portfolio_tool",
    "get_portfolio_tool_handler",
    "add_holding_tool",
    "add_holding_tool_handler",
    "update_holding_tool",
    "update_holding_tool_handler",
    "remove_holding_tool",
    "remove_holding_tool_handler",
    "clear_portfolio_tool",
    "clear_portfolio_tool_handler",
    "PRICE_CACHE_TTL",
    "TICKER_PATTERN",

    # Stock Analysis
    "calculate_rsi",
    "format_market_cap",
    "determine_trend",
    "get_stock_data_tool",
    "get_stock_data_tool_handler",
    "get_stock_history_tool",
    "get_stock_history_tool_handler",
    "get_financials_tool",
    "get_financials_tool_handler",
    "FINANCIALS_CACHE_TTL",

    # SEC Edgar
    "get_sec_filings_tool",
    "get_sec_filings_tool_handler",
    "SEC_FILINGS_CACHE_TTL",

    # Triggers
    "create_trigger_tool",
    "create_trigger_tool_handler",
    "list_triggers_tool",
    "list_triggers_tool_handler",
    "update_trigger_tool",
    "update_trigger_tool_handler",
    "delete_trigger_tool",
    "delete_trigger_tool_handler",

    # Web Search
    "web_search_tool",
    "web_search_tool_handler",
    "_tavily_search",
    "_duckduckgo_search",

    # Web Crawl
    "web_crawl_tool",
    "web_crawl_tool_handler",
    "_is_valid_url",
    "_crawl4ai_fetch",
    "_jina_reader_fetch",

    # Reddit Search
    "reddit_search_tool",
    "reddit_search_tool_handler",
    "_praw_search_sync",
    "_reddit_json_search",

    # Home Assistant
    "home_assistant_query_tool",
    "home_assistant_query_handler",
    "home_assistant_control_tool",
    "home_assistant_control_handler",
    "send_voice_message_to_smart_home_tool",
    "send_voice_message_to_smart_home_handler",
    "HomeAssistantClient",
    "AllowlistValidator",
    "get_allowlist_validator",
    "reset_allowlist_validator",
    "reset_voice_message_cooldown",
    "_set_voice_cooldown",
    "_get_redis_client",
    "VOICE_COOLDOWN_REDIS_KEY",
    "map_action_to_service",
    "build_ssml_message",
    "get_voice_delivery_method",
    "VOICE_TYPES",
    "VOICE_MESSAGE_COOLDOWN_SECONDS",
]
