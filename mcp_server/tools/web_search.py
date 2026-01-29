"""
Web Search Tool (Epic 15 - Story 15.1)

Provides web search functionality using Tavily (primary) with DuckDuckGo fallback.
This module implements a resilient search strategy that automatically falls back
to DuckDuckGo if Tavily fails or is unavailable.

Features:
- Tavily as primary search provider with relevance scoring
- DuckDuckGo as fallback when Tavily fails
- Circuit breaker: 8-hour cooldown when Tavily hits usage limits
- Domain filtering (include/exclude) for both providers
"""

from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
import asyncio
import json
import os
import time
import httpx
import redis.asyncio as redis

from mcp_server.config import get_config
from mcp_server.logging import get_logger

logger = get_logger(__name__)

# Redis configuration
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

# Circuit breaker: 1 hour when Tavily hits usage limits
CIRCUIT_BREAKER_TTL = 3600  # 1 hour in seconds
CIRCUIT_BREAKER_KEY = "tavily:circuit_breaker"


def _get_redis_client() -> Optional[redis.Redis]:
    """Create async Redis client for circuit breaker."""
    try:
        return redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True
        )
    except Exception as e:
        logger.warning(f"Failed to create Redis client: {e}")
        return None


async def _is_circuit_open() -> bool:
    """Check if circuit breaker is open (Tavily should be skipped)."""
    redis_client = None
    try:
        redis_client = _get_redis_client()
        if not redis_client:
            return False
        value = await redis_client.get(CIRCUIT_BREAKER_KEY)
        if value:
            data = json.loads(value)
            logger.info(
                "tavily.circuit_breaker.open",
                extra={"reason": data.get("reason"), "opened_at": data.get("opened_at")}
            )
            return True
        return False
    except Exception as e:
        logger.warning(f"Circuit breaker check failed: {e}")
        return False
    finally:
        if redis_client:
            await redis_client.aclose()


async def _open_circuit(reason: str) -> None:
    """Open circuit breaker to skip Tavily for 8 hours."""
    redis_client = None
    try:
        redis_client = _get_redis_client()
        if not redis_client:
            return
        await redis_client.setex(
            CIRCUIT_BREAKER_KEY,
            CIRCUIT_BREAKER_TTL,
            json.dumps({"reason": reason, "opened_at": time.time()})
        )
        logger.warning(
            "tavily.circuit_breaker.opened",
            extra={"reason": reason, "ttl_hours": CIRCUIT_BREAKER_TTL / 3600}
        )
    except Exception as e:
        logger.warning(f"Failed to open circuit breaker: {e}")
    finally:
        if redis_client:
            await redis_client.aclose()


def _extract_domain(url: str) -> str:
    """Extract domain from URL, removing www. prefix."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def _matches_domain_filter(url: str, include_domains: List[str], exclude_domains: List[str]) -> bool:
    """
    Check if URL matches domain filters.

    Args:
        url: The URL to check
        include_domains: If non-empty, URL must match one of these domains
        exclude_domains: URL must not match any of these domains

    Returns:
        True if URL passes the filters, False otherwise
    """
    domain = _extract_domain(url)
    if not domain:
        return False

    # Normalize filter domains (remove www., lowercase)
    normalized_include = [d.lower().removeprefix("www.") for d in include_domains]
    normalized_exclude = [d.lower().removeprefix("www.") for d in exclude_domains]

    # Check exclude list first
    for excluded in normalized_exclude:
        if domain == excluded or domain.endswith("." + excluded):
            return False

    # If include list is specified, domain must match
    if normalized_include:
        for included in normalized_include:
            if domain == included or domain.endswith("." + included):
                return True
        return False

    return True


def _filter_results_by_domain(
    results: List[Dict[str, Any]],
    include_domains: List[str],
    exclude_domains: List[str],
    max_results: int
) -> List[Dict[str, Any]]:
    """
    Filter search results by domain and limit to max_results.

    Args:
        results: List of search result dicts with 'url' field
        include_domains: Only include results from these domains
        exclude_domains: Exclude results from these domains
        max_results: Maximum results to return

    Returns:
        Filtered list of results
    """
    if not include_domains and not exclude_domains:
        return results[:max_results]

    filtered = []
    for result in results:
        url = result.get("url", "")
        if _matches_domain_filter(url, include_domains, exclude_domains):
            filtered.append(result)
            if len(filtered) >= max_results:
                break

    return filtered


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

            # Tavily returns 432 for usage limit exceeded
            if response.status_code == 432:
                try:
                    data = response.json()
                    error_msg = data.get("detail", {}).get("error", "Usage limit exceeded")
                except Exception:
                    error_msg = "Usage limit exceeded"
                return {
                    "status": "error",
                    "provider": "tavily",
                    "error_message": error_msg,
                    "error_code": "USAGE_LIMIT"
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


async def _duckduckgo_search(
    query: str,
    max_results: int,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    timeout: float = 60.0
) -> Dict[str, Any]:
    """
    Search using DuckDuckGo as fallback.

    Note: duckduckgo-search is synchronous, run in executor with timeout.
    Domain filtering is applied post-search since DDG doesn't support it natively.

    Args:
        query: Search query string
        max_results: Maximum results to return
        include_domains: Only include results from these domains (post-filtered)
        exclude_domains: Exclude results from these domains (post-filtered)
        timeout: Timeout in seconds (default: 60s)

    Returns:
        dict with status, provider, query, and results array
    """
    include_domains = include_domains or []
    exclude_domains = exclude_domains or []
    has_filters = bool(include_domains or exclude_domains)

    # Request more results if filtering, to ensure we have enough after filtering
    fetch_count = max_results * 3 if has_filters else max_results

    try:
        # Lazy import to avoid loading the library unless needed
        from ddgs import DDGS

        def _sync_search():
            ddgs = DDGS()
            return list(ddgs.text(query, max_results=fetch_count))

        # Run sync library in executor with timeout to prevent hanging
        loop = asyncio.get_running_loop()
        raw_results = await asyncio.wait_for(
            loop.run_in_executor(None, _sync_search),
            timeout=timeout
        )

        # Convert to standard format
        results = [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
                "score": None  # DDG doesn't provide relevance scores
            }
            for r in raw_results
        ]

        # Apply domain filtering
        if has_filters:
            results = _filter_results_by_domain(
                results, include_domains, exclude_domains, max_results
            )
        else:
            results = results[:max_results]

        return {
            "status": "success",
            "provider": "duckduckgo",
            "query": query,
            "results": results
        }
    except asyncio.TimeoutError:
        logger.error(f"DuckDuckGo search timed out after {timeout}s")
        return {
            "status": "error",
            "provider": "duckduckgo",
            "query": query,
            "results": [],
            "error_message": f"Search timed out after {timeout} seconds",
            "error_code": "TIMEOUT"
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

    # Validate query is not empty
    if not query or not query.strip():
        return {
            "status": "error",
            "provider": "none",
            "query": query or "",
            "results": [],
            "error_message": "Query cannot be empty",
            "error_code": "INVALID_QUERY"
        }

    # Validate and cap max_results to range 1-10
    max_results = max(1, min(max_results, 10))

    # Validate search_depth
    if search_depth not in ("basic", "advanced"):
        search_depth = "basic"

    try:
        config = get_config()
        tavily_api_key = config.get("TAVILY_API_KEY")

        # Check circuit breaker before trying Tavily
        circuit_open = await _is_circuit_open()

        if tavily_api_key and not circuit_open:
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

            # Check if we should open the circuit breaker
            error_code = result.get("error_code", "")
            if error_code in ("RATE_LIMIT", "USAGE_LIMIT"):
                await _open_circuit(result.get("error_message", error_code))

            # Tavily failed, fall through to DuckDuckGo
            logger.warning(
                "web_search.fallback",
                extra={
                    "primary": "tavily",
                    "fallback": "duckduckgo",
                    "reason": result.get("error_message", "unknown")
                }
            )
        elif circuit_open:
            logger.info(
                "web_search.circuit_breaker_active",
                extra={"query": query, "skipping": "tavily"}
            )
    except Exception as e:
        logger.warning(f"Tavily search failed: {e}, falling back to DDG")

    # Fallback to DuckDuckGo (with domain filtering support)
    result = await _duckduckgo_search(
        query=query,
        max_results=max_results,
        include_domains=include_domains or [],
        exclude_domains=exclude_domains or []
    )

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
    "description": """Search the web when you don't have a specific URL.

Use this tool to FIND information — news, facts, products, prices, opinions, or anything you need to look up.
Returns a list of results with titles, URLs, and snippets.

Do NOT use this tool if you already have a URL. Use web_crawl instead to read a known URL.""",
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
