"""
Web Crawl Tools

Provides tools for fetching and parsing webpage content using crawl4ai
with Jina Reader as a fallback.
"""

import asyncio
import re
import time
import uuid
from typing import Any, Dict
from urllib.parse import urlparse

import httpx

from mcp_server.config import get_config
from mcp_server.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# URL Validation
# =============================================================================

def _is_valid_url(url: str) -> bool:
    """
    Validate URL format for security.

    - Must be HTTP or HTTPS
    - Must have a valid domain
    - Block private/internal IP ranges (SSRF protection)

    Args:
        url: URL string to validate

    Returns:
        True if valid, False otherwise
    """
    try:
        parsed = urlparse(url)

        # Must be http or https
        if parsed.scheme not in ("http", "https"):
            return False

        # Must have a netloc (domain)
        if not parsed.netloc:
            return False

        # Block internal/private IP addresses (security - SSRF protection)
        hostname = parsed.hostname or ""

        # Block localhost variants
        if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
            return False

        # Block private IP ranges (10.x.x.x, 172.16-31.x.x, 192.168.x.x)
        if hostname.startswith("10."):
            return False
        if hostname.startswith("192.168."):
            return False
        if hostname.startswith(("172.16.", "172.17.", "172.18.", "172.19.",
                                "172.20.", "172.21.", "172.22.", "172.23.",
                                "172.24.", "172.25.", "172.26.", "172.27.",
                                "172.28.", "172.29.", "172.30.", "172.31.")):
            return False

        # Block link-local addresses (169.254.x.x)
        if hostname.startswith("169.254."):
            return False

        return True
    except Exception:
        return False


# =============================================================================
# Crawl4AI Fetch
# =============================================================================

async def _crawl4ai_fetch(
    url: str,
    include_images: bool,
    max_length: int,
    wait_for_js: bool,
    request_id: str
) -> Dict[str, Any]:
    """
    Fetch page content using crawl4ai.

    Args:
        url: URL to crawl
        include_images: Include image descriptions
        max_length: Maximum content length
        wait_for_js: Wait for JavaScript rendering
        request_id: Request ID for logging

    Returns:
        Dict with crawl result

    Raises:
        Exception: On crawl failure
    """
    # Lazy import of crawl4ai to avoid import overhead when not needed
    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
        from crawl4ai.content_filter_strategy import PruningContentFilter
        from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
    except ImportError as e:
        logger.error(
            "crawl4ai not installed",
            extra={"request_id": request_id, "error": str(e)}
        )
        raise Exception("crawl4ai library not available")

    # Configure markdown generator with content filter for cleaner extraction
    # PruningContentFilter removes boilerplate (nav, footer) while preserving article content
    md_generator = DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(
            threshold=0.48,  # Default recommended threshold
            threshold_type="dynamic"  # Context-aware scoring
        )
    )

    browser_config = BrowserConfig(headless=True)
    run_config = CrawlerRunConfig(
        wait_until="domcontentloaded" if not wait_for_js else "networkidle",
        excluded_tags=["nav", "footer", "header"],  # Remove navigation elements
        markdown_generator=md_generator
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url=url,
            config=run_config
        )

        # Check if crawl was successful
        if not result.success:
            error_msg = getattr(result, 'error_message', 'Unknown error')
            raise Exception(f"Crawl failed: {error_msg}")

        # Extract content using fit_markdown (filtered) with fallback to raw_markdown
        # fit_markdown removes nav/footer boilerplate, raw_markdown is unfiltered
        content = ""
        if hasattr(result, 'markdown') and result.markdown:
            # Try fit_markdown first (clean, filtered content)
            if hasattr(result.markdown, 'fit_markdown') and result.markdown.fit_markdown:
                content = result.markdown.fit_markdown
            # Fallback to raw_markdown if fit_markdown is empty
            elif hasattr(result.markdown, 'raw_markdown') and result.markdown.raw_markdown:
                content = result.markdown.raw_markdown
            # Legacy fallback for older crawl4ai versions
            elif isinstance(result.markdown, str):
                content = result.markdown

        # If content is empty, page may be non-HTML or require JavaScript
        if not content or content.strip() == "":
            return {
                "status": "error",
                "provider": "crawl4ai",
                "url": url,
                "error_message": "No content extracted. Page may be empty or require JavaScript."
            }

        truncated = False

        # Truncate if exceeds max_length
        if len(content) > max_length:
            content = content[:max_length]
            truncated = True

        # Extract title from metadata or content
        title = ""
        if hasattr(result, 'metadata') and result.metadata:
            title = result.metadata.get("title", "")
        if not title:
            # Try to extract from markdown (first # heading)
            title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
            if title_match:
                title = title_match.group(1).strip()

        # Build metadata
        metadata = {}
        if hasattr(result, 'metadata') and result.metadata:
            metadata = {
                "description": result.metadata.get("description"),
                "author": result.metadata.get("author"),
                "published_date": result.metadata.get("published_date"),
            }

        # Include full links in metadata so LLMs can discover and follow them
        # This preserves link discovery even when nav is filtered from content
        links = {"internal": [], "external": []}
        if hasattr(result, 'links') and result.links:
            links = {
                "internal": result.links.get("internal", []),
                "external": result.links.get("external", [])
            }
        metadata["links"] = links
        metadata["links_count"] = len(links["internal"]) + len(links["external"])

        return {
            "status": "success",
            "provider": "crawl4ai",
            "url": url,
            "title": title,
            "content": content,
            "metadata": metadata,
            "truncated": truncated
        }


# =============================================================================
# Jina Reader Fetch (Fallback)
# =============================================================================

async def _jina_reader_fetch(url: str, max_length: int, request_id: str) -> Dict[str, Any]:
    """
    Fetch page content using Jina Reader as fallback.

    Jina Reader converts any URL to clean markdown via:
    GET https://r.jina.ai/{url}

    Args:
        url: URL to fetch
        max_length: Maximum content length
        request_id: Request ID for logging

    Returns:
        Dict with crawl result
    """
    try:
        config = get_config()
        jina_api_key = config.get("JINA_API_KEY", "")
    except Exception:
        jina_api_key = ""

    headers = {
        "User-Agent": "annie-bot/1.0",
        "Accept": "text/plain"
    }
    if jina_api_key:
        headers["Authorization"] = f"Bearer {jina_api_key}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Jina Reader URL format: https://r.jina.ai/{url}
            jina_url = f"https://r.jina.ai/{url}"

            response = await client.get(
                jina_url,
                headers=headers,
                follow_redirects=True
            )

            if response.status_code != 200:
                return {
                    "status": "error",
                    "provider": "jina",
                    "url": url,
                    "error_message": f"Jina Reader returned HTTP {response.status_code}"
                }

            content = response.text
            truncated = False

            # Truncate if exceeds max_length
            if len(content) > max_length:
                content = content[:max_length]
                truncated = True

            # Try to extract title from markdown (first # heading)
            title = ""
            title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
            if title_match:
                title = title_match.group(1).strip()

            return {
                "status": "success",
                "provider": "jina",
                "url": url,
                "title": title,
                "content": content,
                "metadata": {
                    "description": None,
                    "author": None,
                    "published_date": None,
                    "links_count": 0
                },
                "truncated": truncated
            }

    except httpx.TimeoutException:
        return {
            "status": "error",
            "provider": "jina",
            "url": url,
            "error_message": "Jina Reader request timed out (15s limit)"
        }
    except httpx.HTTPError as e:
        return {
            "status": "error",
            "provider": "jina",
            "url": url,
            "error_message": f"Network error: {str(e)}"
        }
    except Exception as e:
        return {
            "status": "error",
            "provider": "jina",
            "url": url,
            "error_message": str(e)
        }


# =============================================================================
# Web Crawl Tool Handler
# =============================================================================

async def web_crawl_tool_handler(
    url: str,
    include_images: bool = False,
    max_length: int = 10000,
    wait_for_js: bool = False
) -> Dict[str, Any]:
    """
    Fetch and parse webpage content using crawl4ai with Jina fallback.

    This tool crawls a webpage and returns clean markdown content suitable
    for LLM consumption. Uses crawl4ai as the primary provider with Jina
    Reader as a fallback for blocked or problematic sites.

    Args:
        url: URL to crawl (must be http:// or https://)
        include_images: Include image descriptions (default: False)
        max_length: Maximum content length in characters (default: 10000)
        wait_for_js: Wait for JavaScript to render (default: False, adds latency)

    Returns:
        Dict with:
        - status: "success" or "error"
        - provider: "crawl4ai" or "jina"
        - url: The crawled URL
        - title: Page title
        - content: Clean markdown content
        - metadata: Description, author, published_date, links_count
        - truncated: True if content was truncated
        - error_message: Error details (on failure)
    """
    start_time = time.time()
    request_id = str(uuid.uuid4())[:8]

    # Validate URL format
    if not _is_valid_url(url):
        logger.warning(
            "Invalid URL provided to web_crawl",
            extra={"url": url, "request_id": request_id}
        )
        return {
            "status": "error",
            "provider": None,
            "url": url,
            "error_message": "Invalid URL format. Please provide a valid HTTP/HTTPS URL (localhost and private IPs are blocked)."
        }

    # Try crawl4ai first
    try:
        result = await _crawl4ai_fetch(url, include_images, max_length, wait_for_js, request_id)
        duration_ms = int((time.time() - start_time) * 1000)

        if result.get("status") == "success":
            logger.info(
                "web_crawl completed via crawl4ai",
                extra={
                    "provider": "crawl4ai",
                    "url": url,
                    "duration_ms": duration_ms,
                    "content_length": len(result.get("content", "")),
                    "truncated": result.get("truncated", False),
                    "request_id": request_id
                }
            )
            return result
        else:
            # crawl4ai returned an error result, try Jina
            logger.warning(
                "crawl4ai returned error, falling back to Jina Reader",
                extra={
                    "url": url,
                    "error": result.get("error_message"),
                    "request_id": request_id
                }
            )
            raise Exception(result.get("error_message", "crawl4ai error"))

    except Exception as e:
        logger.warning(
            "crawl4ai failed, falling back to Jina Reader",
            extra={
                "url": url,
                "error": str(e),
                "error_type": type(e).__name__,
                "request_id": request_id
            }
        )

        # Fall back to Jina Reader
        try:
            result = await _jina_reader_fetch(url, max_length, request_id)
            duration_ms = int((time.time() - start_time) * 1000)

            if result.get("status") == "success":
                logger.info(
                    "web_crawl completed via Jina fallback",
                    extra={
                        "provider": "jina",
                        "url": url,
                        "duration_ms": duration_ms,
                        "content_length": len(result.get("content", "")),
                        "truncated": result.get("truncated", False),
                        "request_id": request_id
                    }
                )
            else:
                logger.error(
                    "Both crawl4ai and Jina Reader failed",
                    extra={
                        "url": url,
                        "crawl4ai_error": str(e),
                        "jina_error": result.get("error_message"),
                        "duration_ms": duration_ms,
                        "request_id": request_id
                    }
                )

            return result

        except Exception as jina_error:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Both crawl4ai and Jina Reader failed",
                extra={
                    "url": url,
                    "crawl4ai_error": str(e),
                    "jina_error": str(jina_error),
                    "duration_ms": duration_ms,
                    "request_id": request_id
                }
            )
            return {
                "status": "error",
                "provider": None,
                "url": url,
                "error_message": f"Failed to fetch URL: {str(jina_error)}"
            }


# =============================================================================
# Web Crawl Tool Definition
# =============================================================================

web_crawl_tool = {
    "name": "web_crawl",
    "description": """Fetch and read the full content of a webpage.

Use this tool when you need to:
- Read an article, blog post, or news story
- Access documentation or reference material
- Get the full content of a URL the user references
- Read product pages, reviews, or detailed information

Returns clean markdown text suitable for LLM consumption. Supports JavaScript-rendered pages with wait_for_js option.

IMPORTANT: This tool is for reading webpage content. For searching the web, use web_search instead.

Examples:
- User shares a link: "Read this article for me: https://example.com/article"
- User references a page: "What does the React docs say about hooks?"
- User wants details: "Can you summarize this blog post?"
""",
    "inputSchema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to crawl and extract content from (must be http:// or https://)"
            },
            "include_images": {
                "type": "boolean",
                "description": "Include image descriptions in output (default: false)",
                "default": False
            },
            "max_length": {
                "type": "integer",
                "description": "Maximum content length in characters (default: 10000, prevents context overflow)",
                "default": 10000
            },
            "wait_for_js": {
                "type": "boolean",
                "description": "Wait for JavaScript to render before extracting content. Use for SPAs or dynamic pages. Adds 1-2s latency. (default: false)",
                "default": False
            }
        },
        "required": ["url"]
    },
    "handler": web_crawl_tool_handler
}
