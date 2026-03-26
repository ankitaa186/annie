"""
Reddit Search Tool for MCP Server

This module provides Reddit search functionality using PRAW (Python Reddit API Wrapper)
with OAuth for full-featured access. Falls back to Reddit's public JSON API when
PRAW is unavailable or fails.

Epic 15 - Story 15.3
"""

import asyncio
import time
from typing import Any, Dict

import httpx

from mcp_server.config import get_config
from mcp_server.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Reddit JSON API Cooldown Tracking
# =============================================================================

# Prevents repeated requests when IP is blocked (HTTP 429 or connection errors)
_reddit_json_api_cooldown_until: float = 0.0  # Unix timestamp when cooldown expires
REDDIT_JSON_API_COOLDOWN_SECONDS = 3600  # 1 hour cooldown after failure


def _is_reddit_json_api_in_cooldown() -> tuple[bool, int]:
    """
    Check if Reddit JSON API is in cooldown period.

    Returns:
        Tuple of (is_in_cooldown, seconds_remaining)
    """
    global _reddit_json_api_cooldown_until
    now = time.time()
    if now < _reddit_json_api_cooldown_until:
        remaining = int(_reddit_json_api_cooldown_until - now)
        return True, remaining
    return False, 0


def _set_reddit_json_api_cooldown():
    """Set cooldown for Reddit JSON API after a failure."""
    global _reddit_json_api_cooldown_until
    _reddit_json_api_cooldown_until = time.time() + REDDIT_JSON_API_COOLDOWN_SECONDS
    logger.warning(
        f"Reddit JSON API cooldown activated for {REDDIT_JSON_API_COOLDOWN_SECONDS} seconds",
        extra={
            "event": "reddit_json_api.cooldown_set",
            "cooldown_seconds": REDDIT_JSON_API_COOLDOWN_SECONDS,
            "cooldown_until": _reddit_json_api_cooldown_until
        }
    )


# =============================================================================
# PRAW Search (Synchronous)
# =============================================================================


def _praw_search_sync(
    query: str,
    subreddit: str,
    sort: str,
    time_filter: str,
    limit: int,
    include_comments: bool,
    client_id: str,
    client_secret: str,
    user_agent: str
) -> Dict[str, Any]:
    """
    Synchronous PRAW search function to be run in executor.

    PRAW is synchronous and must be run in a thread pool to avoid blocking
    the event loop.

    Args:
        query: Search query string
        subreddit: Subreddit name (without r/ prefix) or None for "all"
        sort: Sort order (relevance, hot, top, new)
        time_filter: Time filter (hour, day, week, month, year, all)
        limit: Maximum results to return
        include_comments: Whether to include top comments
        client_id: Reddit OAuth client ID
        client_secret: Reddit OAuth client secret
        user_agent: User agent string

    Returns:
        dict: Search results with provider="praw"
    """
    # Lazy import of praw to avoid loading it when not needed
    import praw
    from prawcore.exceptions import (
        Forbidden,
        NotFound,
        TooManyRequests,
        ServerError,
        RequestException
    )

    try:
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent
        )

        # Get subreddit - use "all" if none specified
        sub = reddit.subreddit(subreddit if subreddit else "all")

        results = []
        for submission in sub.search(query, sort=sort, time_filter=time_filter, limit=limit):
            # Build post data
            post = {
                "type": "post",
                "title": submission.title,
                "subreddit": f"r/{submission.subreddit.display_name}",
                "author": f"u/{submission.author.name}" if submission.author else "[deleted]",
                "score": submission.score,
                "url": f"https://reddit.com{submission.permalink}",
                "selftext": submission.selftext[:1000] if submission.selftext else None,
                "num_comments": submission.num_comments,
                "created_utc": submission.created_utc,
                "comments": []
            }

            # Include top comments if requested
            if include_comments:
                try:
                    # Replace "more comments" links with empty to avoid extra API calls
                    submission.comments.replace_more(limit=0)
                    for comment in submission.comments[:5]:
                        # Skip deleted/removed comments
                        if comment.author is None:
                            continue
                        post["comments"].append({
                            "author": f"u/{comment.author.name}" if comment.author else "[deleted]",
                            "score": comment.score,
                            "body": comment.body[:500],
                            "replies_count": len(comment.replies) if hasattr(comment, 'replies') else 0
                        })
                except Exception as e:
                    # Log but continue - comments are optional
                    logger.warning(f"Failed to fetch comments: {e}")

            results.append(post)

        return {
            "status": "success",
            "provider": "praw",
            "query": query,
            "subreddit": subreddit or "all",
            "results": results
        }

    except Forbidden as e:
        # Private subreddit or banned
        return {
            "status": "error",
            "provider": "praw",
            "query": query,
            "error_message": f"Subreddit is private or access forbidden: {str(e)}",
            "error_code": "FORBIDDEN"
        }

    except NotFound as e:
        # Subreddit doesn't exist
        return {
            "status": "error",
            "provider": "praw",
            "query": query,
            "error_message": f"Subreddit not found: {str(e)}",
            "error_code": "NOT_FOUND"
        }

    except TooManyRequests as e:
        # Rate limited - PRAW usually handles this, but just in case
        return {
            "status": "error",
            "provider": "praw",
            "query": query,
            "error_message": f"Rate limited by Reddit: {str(e)}",
            "error_code": "RATE_LIMITED"
        }

    except (ServerError, RequestException) as e:
        # Server error or request failed
        return {
            "status": "error",
            "provider": "praw",
            "query": query,
            "error_message": f"Reddit API error: {str(e)}",
            "error_code": "API_ERROR"
        }

    except Exception as e:
        # Unexpected error - let caller handle fallback
        return {
            "status": "error",
            "provider": "praw",
            "query": query,
            "error_message": f"PRAW error: {str(e)}",
            "error_code": "PRAW_ERROR"
        }


# =============================================================================
# Reddit JSON API Search (Async Fallback)
# =============================================================================


async def _reddit_json_search(
    query: str,
    subreddit: str,
    sort: str,
    time_filter: str,
    limit: int,
    user_agent: str
) -> Dict[str, Any]:
    """
    Search Reddit using public JSON API as fallback.

    This doesn't require authentication but has limitations:
    - Cannot include comments in search results
    - More aggressive rate limiting
    - Less reliable than OAuth

    Args:
        query: Search query string
        subreddit: Subreddit name (without r/ prefix) or None for "all"
        sort: Sort order (relevance, hot, top, new)
        time_filter: Time filter (hour, day, week, month, year, all)
        limit: Maximum results to return
        user_agent: User agent string

    Returns:
        dict: Search results with provider="json_api"
    """
    try:
        base_url = "https://www.reddit.com"
        if subreddit:
            url = f"{base_url}/r/{subreddit}/search.json"
        else:
            url = f"{base_url}/search.json"

        params = {
            "q": query,
            "sort": sort,
            "t": time_filter,
            "limit": min(limit, 25),
            "restrict_sr": "on" if subreddit else "off"
        }

        headers = {"User-Agent": user_agent}

        # Retry with exponential backoff for rate limiting
        max_retries = 3
        retry_delays = [1, 2, 4]

        async with httpx.AsyncClient(timeout=15.0) as client:
            for attempt in range(max_retries):
                response = await client.get(
                    url,
                    params=params,
                    headers=headers,
                    follow_redirects=True
                )

                if response.status_code == 429:
                    # Rate limited - wait and retry
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Reddit JSON API rate limited, retrying in {retry_delays[attempt]}s",
                            extra={"attempt": attempt + 1, "query": query}
                        )
                        await asyncio.sleep(retry_delays[attempt])
                        continue
                    else:
                        return {
                            "status": "error",
                            "provider": "json_api",
                            "query": query,
                            "error_message": "Rate limited after retries",
                            "error_code": "RATE_LIMITED"
                        }

                if response.status_code == 403:
                    return {
                        "status": "error",
                        "provider": "json_api",
                        "query": query,
                        "error_message": "Subreddit is private or access forbidden",
                        "error_code": "FORBIDDEN"
                    }

                if response.status_code == 404:
                    return {
                        "status": "error",
                        "provider": "json_api",
                        "query": query,
                        "error_message": f"Subreddit not found: {subreddit}",
                        "error_code": "NOT_FOUND"
                    }

                if response.status_code != 200:
                    return {
                        "status": "error",
                        "provider": "json_api",
                        "query": query,
                        "error_message": f"HTTP {response.status_code}",
                        "error_code": "HTTP_ERROR"
                    }

                # Success - parse response
                break

            data = response.json()
            results = []

            for post_data in data.get("data", {}).get("children", []):
                post = post_data.get("data", {})

                # Skip deleted posts
                author = post.get("author", "[deleted]")
                if author == "[deleted]":
                    continue

                results.append({
                    "type": "post",
                    "title": post.get("title"),
                    "subreddit": f"r/{post.get('subreddit')}",
                    "author": f"u/{author}",
                    "score": post.get("score", 0),
                    "url": f"https://reddit.com{post.get('permalink')}",
                    "selftext": (post.get("selftext", "") or "")[:1000],
                    "num_comments": post.get("num_comments", 0),
                    "created_utc": post.get("created_utc"),
                    "comments": []  # JSON API doesn't include comments in search
                })

            return {
                "status": "success",
                "provider": "json_api",
                "query": query,
                "subreddit": subreddit or "all",
                "results": results,
                "note": "Comments not available via JSON API fallback"
            }

    except httpx.TimeoutException:
        return {
            "status": "error",
            "provider": "json_api",
            "query": query,
            "error_message": "Request timed out",
            "error_code": "TIMEOUT"
        }

    except Exception as e:
        return {
            "status": "error",
            "provider": "json_api",
            "query": query,
            "error_message": str(e),
            "error_code": "INTERNAL_ERROR"
        }


# =============================================================================
# Reddit Search Tool Handler
# =============================================================================


async def reddit_search_tool_handler(
    query: str,
    subreddit: str = None,
    search_type: str = "posts",
    sort: str = "relevance",
    time_filter: str = "all",
    limit: int = 10,
    include_comments: bool = True
) -> Dict[str, Any]:
    """
    Search Reddit for posts, comments, and community discussions.

    Uses PRAW (Python Reddit API Wrapper) with OAuth for full-featured access
    when credentials are configured. Falls back to Reddit's public JSON API
    when PRAW is unavailable or fails.

    Args:
        query: Search query string
        subreddit: Limit search to specific subreddit (without r/ prefix)
        search_type: Type of content to search (posts, comments, subreddits) - currently only posts supported
        sort: Sort order (relevance, hot, top, new). Default: relevance
        time_filter: Time filter (hour, day, week, month, year, all). Default: all
        limit: Maximum results (1-25). Default: 10
        include_comments: Include top 5 comments per post (PRAW only). Default: true

    Returns:
        dict: Search results with status, provider, query, subreddit, and results array
    """
    start_time = time.time()

    # Validate parameters
    if not query or not query.strip():
        return {
            "status": "error",
            "error_message": "Query is required",
            "error_code": "VALIDATION_ERROR"
        }

    # Validate sort option
    valid_sorts = ["relevance", "hot", "top", "new"]
    if sort not in valid_sorts:
        return {
            "status": "error",
            "error_message": f"Invalid sort option '{sort}'. Valid options: {', '.join(valid_sorts)}",
            "error_code": "VALIDATION_ERROR"
        }

    # Validate time_filter option
    valid_time_filters = ["hour", "day", "week", "month", "year", "all"]
    if time_filter not in valid_time_filters:
        return {
            "status": "error",
            "error_message": f"Invalid time_filter '{time_filter}'. Valid options: {', '.join(valid_time_filters)}",
            "error_code": "VALIDATION_ERROR"
        }

    # Clamp limit to valid range
    limit = max(1, min(25, limit))

    # Get config for Reddit credentials
    try:
        config = get_config()
    except Exception as e:
        logger.warning(f"Failed to load config: {e}")
        config = {}

    client_id = config.get("REDDIT_CLIENT_ID")
    client_secret = config.get("REDDIT_CLIENT_SECRET")
    user_agent = config.get("REDDIT_USER_AGENT", "annie-bot/1.0")

    logger.info(
        "Starting Reddit search",
        extra={
            "event": "reddit_search.started",
            "query": query,
            "subreddit": subreddit,
            "sort": sort,
            "time_filter": time_filter,
            "limit": limit,
            "include_comments": include_comments,
            "has_praw_credentials": bool(client_id and client_secret)
        }
    )

    result = None

    # Try PRAW first if credentials are available
    if client_id and client_secret:
        try:
            # Run synchronous PRAW in executor to not block event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                _praw_search_sync,
                query,
                subreddit,
                sort,
                time_filter,
                limit,
                include_comments,
                client_id,
                client_secret,
                user_agent
            )

            # Check if PRAW succeeded
            if result.get("status") == "success":
                duration_ms = int((time.time() - start_time) * 1000)
                logger.info(
                    "Reddit search completed via PRAW",
                    extra={
                        "event": "reddit_search.completed",
                        "provider": "praw",
                        "query": query,
                        "subreddit": subreddit,
                        "result_count": len(result.get("results", [])),
                        "duration_ms": duration_ms
                    }
                )
                return result

            # PRAW failed - log and fall through to JSON API
            logger.warning(
                "PRAW search failed, falling back to JSON API",
                extra={
                    "event": "reddit_search.fallback",
                    "query": query,
                    "praw_error": result.get("error_message"),
                    "praw_error_code": result.get("error_code")
                }
            )

        except Exception as e:
            logger.warning(
                f"PRAW search exception, falling back to JSON API: {e}",
                extra={
                    "event": "reddit_search.fallback",
                    "query": query,
                    "exception": str(e)
                }
            )

    # Check if JSON API is in cooldown (to avoid IP blocks from Reddit)
    in_cooldown, cooldown_remaining = _is_reddit_json_api_in_cooldown()
    if in_cooldown:
        logger.warning(
            "Reddit JSON API in cooldown, skipping request",
            extra={
                "event": "reddit_search.cooldown_blocked",
                "query": query,
                "cooldown_remaining_seconds": cooldown_remaining
            }
        )
        return {
            "status": "error",
            "provider": None,
            "query": query,
            "subreddit": subreddit or "all",
            "error_message": f"Reddit API temporarily unavailable. Cooldown expires in {cooldown_remaining // 60} minutes.",
            "error_code": "COOLDOWN_ACTIVE"
        }

    # Fallback to JSON API (no auth required)
    logger.info(
        "Using Reddit JSON API fallback",
        extra={
            "event": "reddit_search.json_api",
            "query": query,
            "subreddit": subreddit,
            "reason": "no_credentials" if not (client_id and client_secret) else "praw_failed"
        }
    )

    result = await _reddit_json_search(
        query=query,
        subreddit=subreddit,
        sort=sort,
        time_filter=time_filter,
        limit=limit,
        user_agent=user_agent
    )

    duration_ms = int((time.time() - start_time) * 1000)

    if result.get("status") == "success":
        logger.info(
            "Reddit search completed via JSON API",
            extra={
                "event": "reddit_search.completed",
                "provider": "json_api",
                "query": query,
                "subreddit": subreddit,
                "result_count": len(result.get("results", [])),
                "duration_ms": duration_ms
            }
        )
    else:
        # Set cooldown on failure (rate limit, connection errors, or persistent failures)
        error_code = result.get("error_code", "")
        cooldown_trigger_codes = ("RATE_LIMITED", "HTTP_ERROR", "TIMEOUT", "FORBIDDEN")
        should_cooldown = error_code in cooldown_trigger_codes

        if should_cooldown:
            _set_reddit_json_api_cooldown()

        logger.error(
            "Reddit search failed",
            extra={
                "event": "reddit_search.failed",
                "query": query,
                "error_message": result.get("error_message"),
                "error_code": error_code,
                "duration_ms": duration_ms,
                "cooldown_activated": should_cooldown
            }
        )

    return result


# =============================================================================
# Reddit Search Tool Definition
# =============================================================================

reddit_search_tool = {
    "name": "reddit_search",
    "description": "Search Reddit for posts, comments, and community discussions. Useful for finding real user experiences, reviews, and opinions on topics. Great for product research, troubleshooting, and understanding public sentiment.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query"
            },
            "subreddit": {
                "type": "string",
                "description": "Limit search to specific subreddit (without r/ prefix)"
            },
            "search_type": {
                "type": "string",
                "enum": ["posts", "comments", "subreddits"],
                "description": "Type of content to search (default: posts)",
                "default": "posts"
            },
            "sort": {
                "type": "string",
                "enum": ["relevance", "hot", "top", "new"],
                "description": "Sort order for results (default: relevance)",
                "default": "relevance"
            },
            "time_filter": {
                "type": "string",
                "enum": ["hour", "day", "week", "month", "year", "all"],
                "description": "Time filter for results (default: all)",
                "default": "all"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results (default: 10, max: 25)",
                "default": 10,
                "minimum": 1,
                "maximum": 25
            },
            "include_comments": {
                "type": "boolean",
                "description": "Include top comments for posts (default: true, PRAW only)",
                "default": True
            }
        },
        "required": ["query"]
    },
    "handler": reddit_search_tool_handler
}
