"""
Web Search Tool (Epic 15 - Story 15.1)

Provides web search functionality using Tavily (primary) with DuckDuckGo fallback.
This module implements a resilient search strategy that automatically falls back
to DuckDuckGo if Tavily fails or is unavailable.
"""

from typing import Any, Dict, List, Optional
import asyncio
import time
import httpx

from mcp_server.config import get_config
from mcp_server.logging import get_logger

logger = get_logger(__name__)


async def _tavily_search(
    query: str,
    max_results: int,
    search_depth: str,
    include_domains: List[str],
    exclude_domains: List[str],
    api_key: str
) -> Dict[str, Any]:
    """
    Execute Tavily search API call.

    Args:
        query: Search query string
        max_results: Maximum results to return (1-10)
        search_depth: "basic" (faster/cheaper) or "advanced" (deeper)
        include_domains: Only include results from these domains
        exclude_domains: Exclude results from these domains
        api_key: Tavily API key

    Returns:
        dict with status, provider, query, and results array (or error info)
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,  # Tavily uses body, not header
                    "query": query,
                    "search_depth": search_depth,
                    "max_results": max_results,
                    "include_domains": include_domains,
                    "exclude_domains": exclude_domains
                }
            )

            if response.status_code == 429:
                return {
                    "status": "error",
                    "provider": "tavily",
                    "error_message": "Rate limit exceeded",
                    "error_code": "RATE_LIMIT"
                }

            if response.status_code >= 500:
                return {
                    "status": "error",
                    "provider": "tavily",
                    "error_message": f"Server error: {response.status_code}",
                    "error_code": "SERVER_ERROR"
                }

            response.raise_for_status()
            data = response.json()

            return {
                "status": "success",
                "provider": "tavily",
                "query": query,
                "results": [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "snippet": r.get("content", ""),
                        "score": r.get("score", None)  # Relevance score if available
                    }
                    for r in data.get("results", [])[:max_results]
                ]
            }
    except httpx.TimeoutException:
        return {
            "status": "error",
            "provider": "tavily",
            "error_message": "Request timed out",
            "error_code": "TIMEOUT"
        }
    except Exception as e:
        return {
            "status": "error",
            "provider": "tavily",
            "error_message": str(e),
            "error_code": "UNKNOWN"
        }


async def _duckduckgo_search(query: str, max_results: int) -> Dict[str, Any]:
    """
    Search using DuckDuckGo as fallback.

    Note: duckduckgo-search is synchronous, run in executor.

    Args:
        query: Search query string
        max_results: Maximum results to return

    Returns:
        dict with status, provider, query, and results array
    """
    try:
        # Lazy import to avoid loading the library unless needed
        from duckduckgo_search import DDGS

        def _sync_search():
            ddgs = DDGS()
            return list(ddgs.text(query, max_results=max_results))

        # Run sync library in executor to not block event loop
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, _sync_search)

        return {
            "status": "success",
            "provider": "duckduckgo",
            "query": query,
            "results": [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                    "score": None  # DDG doesn't provide relevance scores
                }
                for r in results
            ]
        }
    except Exception as e:
        logger.error(f"DuckDuckGo search failed: {e}")
        return {
            "status": "error",
            "provider": "duckduckgo",
            "query": query,
            "results": [],
            "error_message": str(e)
        }


async def web_search_tool_handler(
    query: str,
    max_results: int = 5,
    search_depth: str = "basic",
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Execute web search using Tavily with DuckDuckGo fallback.

    Args:
        query: Search query string
        max_results: Maximum results to return (1-10, default 5)
        search_depth: "basic" (faster/cheaper) or "advanced" (deeper)
        include_domains: Only include results from these domains
        exclude_domains: Exclude results from these domains

    Returns:
        dict with status, provider, query, and results array
    """
    start_time = time.time()

    # Validate and cap max_results to range 1-10
    max_results = max(1, min(max_results, 10))

    # Validate search_depth
    if search_depth not in ("basic", "advanced"):
        search_depth = "basic"

    try:
        config = get_config()
        tavily_api_key = config.get("TAVILY_API_KEY")

        if tavily_api_key:
            result = await _tavily_search(
                query=query,
                max_results=max_results,
                search_depth=search_depth,
                include_domains=include_domains or [],
                exclude_domains=exclude_domains or [],
                api_key=tavily_api_key
            )
            if result["status"] == "success":
                logger.info(
                    "web_search.completed",
                    extra={
                        "query": query,
                        "provider": "tavily",
                        "results_count": len(result.get("results", [])),
                        "duration_ms": int((time.time() - start_time) * 1000)
                    }
                )
                return result
            # Tavily failed, fall through to DuckDuckGo
            logger.warning(
                "web_search.fallback",
                extra={
                    "primary": "tavily",
                    "fallback": "duckduckgo",
                    "reason": result.get("error_message", "unknown")
                }
            )
    except Exception as e:
        logger.warning(f"Tavily search failed: {e}, falling back to DDG")

    # Fallback to DuckDuckGo
    result = await _duckduckgo_search(query, max_results)

    logger.info(
        "web_search.completed",
        extra={
            "query": query,
            "provider": "duckduckgo",
            "results_count": len(result.get("results", [])),
            "duration_ms": int((time.time() - start_time) * 1000)
        }
    )

    return result


# Web search tool definition
web_search_tool = {
    "name": "web_search",
    "description": "Search the web for current information using Tavily (primary) with DuckDuckGo fallback. Returns relevant results with titles, URLs, and snippets. Use for finding up-to-date information about news, products, services, facts, or any topic requiring current web data.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query - be specific for better results"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return (default: 5, max: 10)",
                "default": 5,
                "minimum": 1,
                "maximum": 10
            },
            "search_depth": {
                "type": "string",
                "enum": ["basic", "advanced"],
                "description": "Search depth: 'basic' (faster, cheaper) or 'advanced' (deeper, more thorough)",
                "default": "basic"
            },
            "include_domains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Only include results from these domains (e.g., ['reddit.com', 'stackoverflow.com'])"
            },
            "exclude_domains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Exclude results from these domains (e.g., ['pinterest.com'])"
            }
        },
        "required": ["query"]
    },
    "handler": web_search_tool_handler
}
