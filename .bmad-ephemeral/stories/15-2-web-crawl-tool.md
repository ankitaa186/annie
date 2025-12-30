# Story 15.2: Web Crawl Tool (crawl4ai + Jina Fallback)

Status: done

## Story

**As a** user of Annie,
**I want** Annie to fetch and read full webpage content from URLs,
**So that** she can provide detailed information from specific web pages I reference.

**Epic:** Epic 15 - Extended MCP Tools - Web & Profile
**Prerequisites:** Story 15.1 (for pattern reference)
**Estimated Effort:** 1 day

---

## Acceptance Criteria

### AC #15.2.1: crawl4ai Integration
**Given** the web_crawl tool is called with a URL
**When** crawl4ai is available and can access the page
**Then** the tool uses AsyncWebCrawler to fetch and parse the page content

**Mapped to Tasks:** Task 1

---

### AC #15.2.2: Jina Reader Fallback
**Given** the web_crawl tool is called
**When** crawl4ai fails (parse error, timeout, blocked site)
**Then** the tool falls back to Jina Reader (GET https://r.jina.ai/{url})

**Mapped to Tasks:** Task 2

---

### AC #15.2.3: JavaScript Rendering Option
**Given** the web_crawl tool is called with wait_for_js=True
**When** the page requires JavaScript to render content
**Then** the tool waits for JavaScript execution before extracting content (adds 1-2s latency)

**Mapped to Tasks:** Task 1

---

### AC #15.2.4: Clean Markdown Output
**Given** the web_crawl tool successfully fetches a page
**When** content is extracted
**Then** the output is clean markdown suitable for LLM consumption (no HTML tags, proper formatting)

**Mapped to Tasks:** Task 1, Task 2

---

### AC #15.2.5: Content Length Limiting
**Given** the web_crawl tool fetches content longer than max_length
**When** max_length is specified (default 10000 characters)
**Then** content is truncated at max_length and truncated=True is set in response

**Mapped to Tasks:** Task 1, Task 2

---

### AC #15.2.6: Non-HTML Content Handling
**Given** the web_crawl tool is called with a non-HTML URL (PDF, image, binary)
**When** the content type is not text/html
**Then** a graceful error message is returned explaining the limitation

**Mapped to Tasks:** Task 1

---

### AC #15.2.7: Error Handling
**Given** the web_crawl tool encounters an error
**When** blocked site, timeout (15s), invalid URL, or network error occurs
**Then** appropriate error handling with fallback is applied and structured error response returned

**Mapped to Tasks:** Task 1, Task 2

---

### AC #15.2.8: Unit Tests
**Given** the web_crawl tool implementation
**When** tests are run
**Then** mocked crawl4ai/Jina responses achieve >80% coverage on tool handler code

**Mapped to Tasks:** Task 3

---

### AC #15.2.9: Status Summarizer
**Given** the web_crawl tool is executing
**When** the tool starts and completes
**Then** status updates "Reading webpage..." and "Page loaded ({title})" are emitted via SSE

**Mapped to Tasks:** Task 4

---

## Tasks / Subtasks

### Task 1: Implement crawl4ai Primary Provider
**Status:** DONE
**Acceptance Criteria:** AC #15.2.1, AC #15.2.3, AC #15.2.4, AC #15.2.5, AC #15.2.6, AC #15.2.7

**Implementation Details:**

Add `web_crawl_tool_handler` to `mcp_server/tools.py`:

```python
import re
from urllib.parse import urlparse
from crawl4ai import AsyncWebCrawler

async def web_crawl_tool_handler(
    url: str,
    include_images: bool = False,
    max_length: int = 10000,
    wait_for_js: bool = False
) -> Dict[str, Any]:
    """
    Fetch and parse webpage content using crawl4ai with Jina fallback.

    Args:
        url: URL to crawl
        include_images: Include image descriptions (default: False)
        max_length: Maximum content length in characters (default: 10000)
        wait_for_js: Wait for JavaScript to render (default: False)

    Returns:
        Dict with status, provider, url, title, content, metadata, truncated
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
            "error_message": "Invalid URL format. Please provide a valid HTTP/HTTPS URL."
        }

    try:
        result = await _crawl4ai_fetch(url, include_images, max_length, wait_for_js, request_id)
        duration_ms = int((time.time() - start_time) * 1000)
        logger.info(
            "web_crawl completed",
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
        try:
            result = await _jina_reader_fetch(url, max_length, request_id)
            duration_ms = int((time.time() - start_time) * 1000)
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


def _is_valid_url(url: str) -> bool:
    """
    Validate URL format.

    - Must be HTTP or HTTPS
    - Must have a valid domain
    - Block private/internal IP ranges
    """
    try:
        parsed = urlparse(url)

        # Must be http or https
        if parsed.scheme not in ("http", "https"):
            return False

        # Must have a netloc (domain)
        if not parsed.netloc:
            return False

        # Block internal/private IP addresses (security)
        hostname = parsed.hostname or ""
        if hostname in ("localhost", "127.0.0.1", "0.0.0.0"):
            return False

        # Block private IP ranges
        if hostname.startswith(("10.", "172.16.", "172.17.", "172.18.", "172.19.",
                                "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
                                "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
                                "172.30.", "172.31.", "192.168.")):
            return False

        return True
    except Exception:
        return False


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
    """
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(
            url=url,
            wait_for=wait_for_js,
            timeout=15  # 15 second timeout (JS rendering needs more time)
        )

        # Check for non-HTML content
        content_type = result.metadata.get("content_type", "text/html")
        if not content_type.startswith("text/html"):
            return {
                "status": "error",
                "provider": "crawl4ai",
                "url": url,
                "error_message": f"Cannot parse non-HTML content (type: {content_type}). This tool only supports HTML webpages."
            }

        content = result.markdown
        truncated = False

        # Truncate if exceeds max_length
        if len(content) > max_length:
            content = content[:max_length]
            truncated = True

        return {
            "status": "success",
            "provider": "crawl4ai",
            "url": url,
            "title": result.metadata.get("title", ""),
            "content": content,
            "metadata": {
                "description": result.metadata.get("description"),
                "author": result.metadata.get("author"),
                "published_date": result.metadata.get("published_date"),
                "links_count": len(result.links) if hasattr(result, "links") else 0
            },
            "truncated": truncated
        }
```

**MCP Tool Registration** (add to tool definitions section):

```python
web_crawl_tool = {
    "name": "web_crawl",
    "description": "Fetch and read the full content of a webpage. Use this when you need to read an article, documentation, blog post, or any webpage the user references. Returns clean markdown text. Supports JavaScript-rendered pages with wait_for_js option.",
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
```

**Subtasks:**
- [ ] Add crawl4ai to `mcp_server/requirements.txt`: `crawl4ai>=0.3.0`
- [ ] Implement `_is_valid_url()` validation function
- [ ] Implement `_crawl4ai_fetch()` function with AsyncWebCrawler
- [ ] Handle `wait_for_js` parameter for JavaScript rendering
- [ ] Implement content truncation with `truncated` indicator
- [ ] Handle non-HTML content types with graceful error
- [ ] Add 15s timeout to crawler
- [ ] Block private/internal IP addresses (security)
- [ ] Add structured logging with request_id for tracing
- [ ] Register `web_crawl_tool` in tool registry

---

### Task 2: Implement Jina Reader Fallback
**Status:** DONE
**Acceptance Criteria:** AC #15.2.2, AC #15.2.4, AC #15.2.5, AC #15.2.7

**Implementation Details:**

```python
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
        jina_api_key = config.get("JINA_API_KEY")

        headers = {
            "User-Agent": "annie-bot/1.0",
            "Accept": "text/plain"
        }
        if jina_api_key:
            headers["Authorization"] = f"Bearer {jina_api_key}"

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
```

**Environment Variable** (add to `mcp_server/config.py`):

```python
# Optional: Jina Reader API key for higher rate limits
JINA_API_KEY = os.getenv("JINA_API_KEY", "")
```

**Subtasks:**
- [ ] Implement `_jina_reader_fetch()` function
- [ ] Handle optional `JINA_API_KEY` for authenticated requests
- [ ] Apply content truncation with indicator
- [ ] Extract title from markdown content (first # heading)
- [ ] Handle Jina HTTP errors gracefully
- [ ] Handle timeout errors (15s limit)
- [ ] Handle network errors
- [ ] Add `JINA_API_KEY` to `mcp_server/config.py` (optional)
- [ ] Add `JINA_API_KEY` to `env.example` with description

---

### Task 3: Unit Tests
**Status:** DONE
**Acceptance Criteria:** AC #15.2.8

**Implementation Details:**

Create `mcp_server/tests/test_web_crawl_tool.py`:

```python
"""
Unit tests for web_crawl tool.

Coverage targets:
- crawl4ai success path
- Jina Reader fallback trigger
- JavaScript rendering option
- Content truncation
- Non-HTML content handling
- Error scenarios (timeout, blocked, invalid URL)
- URL validation

Run: pytest mcp_server/tests/test_web_crawl_tool.py -v --cov=mcp_server.tools
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from mcp_server.tools import (
    web_crawl_tool_handler,
    _is_valid_url,
    _crawl4ai_fetch,
    _jina_reader_fetch
)


# ============ Fixtures ============

@pytest.fixture
def mock_crawl4ai_result():
    """Mock crawl4ai result with standard webpage content."""
    result = MagicMock()
    result.markdown = "# Page Title\n\nThis is the page content with some text."
    result.metadata = {
        "title": "Page Title",
        "description": "A test page description",
        "author": "Test Author",
        "published_date": "2025-01-15",
        "content_type": "text/html"
    }
    result.links = [{"href": "https://example.com/link1"}]
    return result


@pytest.fixture
def mock_crawl4ai_pdf_result():
    """Mock crawl4ai result for non-HTML content."""
    result = MagicMock()
    result.markdown = ""
    result.metadata = {
        "title": "",
        "content_type": "application/pdf"
    }
    result.links = []
    return result


@pytest.fixture
def mock_jina_response():
    """Mock httpx response for Jina Reader."""
    response = MagicMock()
    response.status_code = 200
    response.text = "# Jina Title\n\nContent from Jina Reader."
    return response


# ============ URL Validation Tests ============

class TestUrlValidation:
    """Test _is_valid_url function."""

    def test_valid_https_url(self):
        assert _is_valid_url("https://example.com/page") is True

    def test_valid_http_url(self):
        assert _is_valid_url("http://example.com/page") is True

    def test_invalid_ftp_url(self):
        assert _is_valid_url("ftp://example.com/file") is False

    def test_invalid_no_scheme(self):
        assert _is_valid_url("example.com/page") is False

    def test_invalid_localhost(self):
        assert _is_valid_url("http://localhost/page") is False

    def test_invalid_127_0_0_1(self):
        assert _is_valid_url("http://127.0.0.1/page") is False

    def test_invalid_private_ip_10(self):
        assert _is_valid_url("http://10.0.0.1/page") is False

    def test_invalid_private_ip_192(self):
        assert _is_valid_url("http://192.168.1.1/page") is False

    def test_invalid_empty_string(self):
        assert _is_valid_url("") is False

    def test_invalid_malformed(self):
        assert _is_valid_url("not a url") is False


# ============ crawl4ai Tests ============

class TestCrawl4aiFetch:
    """Test crawl4ai primary provider."""

    @pytest.mark.asyncio
    async def test_crawl4ai_success(self, mock_crawl4ai_result):
        """Test successful crawl4ai fetch."""
        with patch("mcp_server.tools.AsyncWebCrawler") as mock_crawler_class:
            mock_crawler = AsyncMock()
            mock_crawler.arun.return_value = mock_crawl4ai_result
            mock_crawler_class.return_value.__aenter__.return_value = mock_crawler

            result = await _crawl4ai_fetch(
                url="https://example.com",
                include_images=False,
                max_length=10000,
                wait_for_js=False,
                request_id="test123"
            )

            assert result["status"] == "success"
            assert result["provider"] == "crawl4ai"
            assert result["title"] == "Page Title"
            assert "Page Title" in result["content"]
            assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_crawl4ai_truncation(self, mock_crawl4ai_result):
        """Test content truncation at max_length."""
        mock_crawl4ai_result.markdown = "A" * 20000  # Long content

        with patch("mcp_server.tools.AsyncWebCrawler") as mock_crawler_class:
            mock_crawler = AsyncMock()
            mock_crawler.arun.return_value = mock_crawl4ai_result
            mock_crawler_class.return_value.__aenter__.return_value = mock_crawler

            result = await _crawl4ai_fetch(
                url="https://example.com",
                include_images=False,
                max_length=5000,
                wait_for_js=False,
                request_id="test123"
            )

            assert result["status"] == "success"
            assert len(result["content"]) == 5000
            assert result["truncated"] is True

    @pytest.mark.asyncio
    async def test_crawl4ai_non_html_content(self, mock_crawl4ai_pdf_result):
        """Test handling of non-HTML content (PDF)."""
        with patch("mcp_server.tools.AsyncWebCrawler") as mock_crawler_class:
            mock_crawler = AsyncMock()
            mock_crawler.arun.return_value = mock_crawl4ai_pdf_result
            mock_crawler_class.return_value.__aenter__.return_value = mock_crawler

            result = await _crawl4ai_fetch(
                url="https://example.com/file.pdf",
                include_images=False,
                max_length=10000,
                wait_for_js=False,
                request_id="test123"
            )

            assert result["status"] == "error"
            assert "non-HTML" in result["error_message"]

    @pytest.mark.asyncio
    async def test_crawl4ai_wait_for_js(self, mock_crawl4ai_result):
        """Test JavaScript rendering option."""
        with patch("mcp_server.tools.AsyncWebCrawler") as mock_crawler_class:
            mock_crawler = AsyncMock()
            mock_crawler.arun.return_value = mock_crawl4ai_result
            mock_crawler_class.return_value.__aenter__.return_value = mock_crawler

            await _crawl4ai_fetch(
                url="https://example.com",
                include_images=False,
                max_length=10000,
                wait_for_js=True,
                request_id="test123"
            )

            # Verify wait_for_js was passed to arun
            mock_crawler.arun.assert_called_once()
            call_kwargs = mock_crawler.arun.call_args[1]
            assert call_kwargs["wait_for"] is True


# ============ Jina Reader Fallback Tests ============

class TestJinaReaderFetch:
    """Test Jina Reader fallback provider."""

    @pytest.mark.asyncio
    async def test_jina_success(self, mock_jina_response):
        """Test successful Jina Reader fetch."""
        with patch("mcp_server.tools.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_jina_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with patch("mcp_server.tools.get_config") as mock_config:
                mock_config.return_value = {}

                result = await _jina_reader_fetch(
                    url="https://example.com",
                    max_length=10000,
                    request_id="test123"
                )

                assert result["status"] == "success"
                assert result["provider"] == "jina"
                assert result["title"] == "Jina Title"
                assert "Content from Jina Reader" in result["content"]

    @pytest.mark.asyncio
    async def test_jina_truncation(self):
        """Test Jina Reader content truncation."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "A" * 20000

        with patch("mcp_server.tools.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with patch("mcp_server.tools.get_config") as mock_config:
                mock_config.return_value = {}

                result = await _jina_reader_fetch(
                    url="https://example.com",
                    max_length=5000,
                    request_id="test123"
                )

                assert len(result["content"]) == 5000
                assert result["truncated"] is True

    @pytest.mark.asyncio
    async def test_jina_http_error(self):
        """Test Jina Reader HTTP error handling."""
        mock_response = MagicMock()
        mock_response.status_code = 503

        with patch("mcp_server.tools.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with patch("mcp_server.tools.get_config") as mock_config:
                mock_config.return_value = {}

                result = await _jina_reader_fetch(
                    url="https://example.com",
                    max_length=10000,
                    request_id="test123"
                )

                assert result["status"] == "error"
                assert "503" in result["error_message"]

    @pytest.mark.asyncio
    async def test_jina_timeout(self):
        """Test Jina Reader timeout handling."""
        import httpx

        with patch("mcp_server.tools.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.TimeoutException("timeout")
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with patch("mcp_server.tools.get_config") as mock_config:
                mock_config.return_value = {}

                result = await _jina_reader_fetch(
                    url="https://example.com",
                    max_length=10000,
                    request_id="test123"
                )

                assert result["status"] == "error"
                assert "timed out" in result["error_message"]


# ============ Integration: Fallback Tests ============

class TestWebCrawlFallback:
    """Test crawl4ai to Jina Reader fallback."""

    @pytest.mark.asyncio
    async def test_fallback_to_jina_on_crawl4ai_failure(self, mock_jina_response):
        """Test fallback to Jina when crawl4ai fails."""
        with patch("mcp_server.tools._crawl4ai_fetch") as mock_crawl4ai:
            mock_crawl4ai.side_effect = Exception("crawl4ai failed")

            with patch("mcp_server.tools._jina_reader_fetch") as mock_jina:
                mock_jina.return_value = {
                    "status": "success",
                    "provider": "jina",
                    "url": "https://example.com",
                    "title": "Fallback Title",
                    "content": "Fallback content",
                    "metadata": {},
                    "truncated": False
                }

                result = await web_crawl_tool_handler(
                    url="https://example.com",
                    max_length=10000
                )

                assert result["status"] == "success"
                assert result["provider"] == "jina"
                mock_jina.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_url_no_fallback(self):
        """Test that invalid URLs return error without fallback attempt."""
        result = await web_crawl_tool_handler(
            url="not-a-valid-url",
            max_length=10000
        )

        assert result["status"] == "error"
        assert "Invalid URL" in result["error_message"]

    @pytest.mark.asyncio
    async def test_localhost_blocked(self):
        """Test that localhost URLs are blocked."""
        result = await web_crawl_tool_handler(
            url="http://localhost:8000/secret",
            max_length=10000
        )

        assert result["status"] == "error"
        assert "Invalid URL" in result["error_message"]
```

**Subtasks:**
- [ ] Create `mcp_server/tests/test_web_crawl_tool.py`
- [ ] Test crawl4ai success path with mocked AsyncWebCrawler
- [ ] Test crawl4ai failure triggers Jina fallback
- [ ] Test `wait_for_js` parameter passed correctly
- [ ] Test content truncation at boundary
- [ ] Test non-HTML content handling (PDF, images)
- [ ] Test error scenarios: timeout, blocked site, invalid URL
- [ ] Test URL validation (valid, invalid, localhost, private IPs)
- [ ] Test Jina Reader success path
- [ ] Test Jina Reader HTTP errors
- [ ] Test Jina Reader timeout handling
- [ ] Run coverage: `pytest mcp_server/tests/test_web_crawl_tool.py -v --cov=mcp_server.tools --cov-report=term-missing`
- [ ] Verify >80% coverage on web_crawl related code

---

### Task 4: Status Summarizer
**Status:** DONE
**Acceptance Criteria:** AC #15.2.9

**Implementation Details:**

Add to `backend/api/status_summarizers.py`:

```python
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


# Register in SUMMARIZERS dict:
SUMMARIZERS["web_crawl"] = summarize_web_crawl_result
```

**Start Status** (emitted before tool execution in `mcp_client.py`):

The start status "Reading webpage..." should be emitted before the tool call via the existing `emit_status` mechanism in `backend/api/mcp_client.py`.

```python
# In execute_tool method, before calling the tool:
if tool_name == "web_crawl":
    await emit_status(conversation_id, "Reading webpage...")
```

**Subtasks:**
- [ ] Implement `summarize_web_crawl_result()` function in `status_summarizers.py`
- [ ] Handle success case with title truncation
- [ ] Handle success case without title
- [ ] Handle error case with message truncation
- [ ] Register `"web_crawl"` in `SUMMARIZERS` dict
- [ ] Add start status "Reading webpage..." emission in `mcp_client.py`
- [ ] Test status summarizer with various result shapes

---

### Task 5: MCP Server Registration
**Status:** DONE
**Acceptance Criteria:** AC #15.2.1 (implicit)

**Implementation Details:**

Register the tool in `mcp_server/server.py`:

```python
# Import the tool handler
from mcp_server.tools import web_crawl_tool, web_crawl_tool_handler

# Register in the tool registry (in initialize_tools function or similar)
registry.register(web_crawl_tool)
```

**Subtasks:**
- [ ] Import `web_crawl_tool` and `web_crawl_tool_handler` in server.py
- [ ] Register tool in the MCP server's tool registry
- [ ] Verify tool appears in `tools/list` response
- [ ] Test tool execution via `tools/call` JSON-RPC method

---

## Definition of Done

- [ ] Task 1-5 completed
- [ ] All 9 acceptance criteria (AC #15.2.1-15.2.9) validated
- [ ] `web_crawl` tool registered in MCP server
- [ ] `crawl4ai` package added to requirements.txt
- [ ] crawl4ai integration working in Docker container
- [ ] Jina Reader fallback working when crawl4ai fails
- [ ] JavaScript rendering option (wait_for_js) working
- [ ] Content truncation with indicator working
- [ ] Non-HTML content handled gracefully with error message
- [ ] URL validation blocks invalid/private URLs
- [ ] Unit tests passing with >80% coverage
- [ ] Status summarizer emitting "Reading webpage..." and "Page loaded (title)"
- [ ] No regressions in other MCP tools
- [ ] Code follows existing patterns in `mcp_server/tools.py`
- [ ] Logging follows structured logging patterns with request_id

---

## Dev Notes

### Architecture Context

**Component Overview:**
- **web_crawl tool** (`mcp_server/tools.py`): MCP tool for web crawling
- **crawl4ai**: Primary local crawler (free, no rate limits)
- **Jina Reader**: Fallback web reader (free tier available)
- **status_summarizers.py**: Real-time status updates

**Flow:**
```
LLM -> web_crawl tool -> crawl4ai (local)
                            |
                            v (on failure)
                       Jina Reader API
                            |
                            v
                    Clean Markdown Output
```

### Technical Constraints

1. **crawl4ai:**
   - Local library, no rate limits
   - JavaScript rendering adds 1-2s latency
   - May be blocked by some sites (Cloudflare, etc.)
   - Requires Playwright dependencies in Docker

2. **Jina Reader:**
   - Free tier available (no API key required)
   - Simple GET request to `r.jina.ai/{url}`
   - Good fallback for blocked sites
   - Optional API key for higher rate limits

3. **Timeout:**
   - 15 seconds per provider (JS rendering needs more time)
   - Total tool timeout: 30 seconds (includes fallback attempt)

4. **Content Size:**
   - Default max_length: 10000 characters
   - Prevents LLM context window overflow
   - Truncation indicator helps LLM understand partial content

5. **Security:**
   - Block localhost/private IPs to prevent SSRF
   - Validate URL scheme (http/https only)

### Dependencies

**Blocking:**
- `crawl4ai>=0.3.0` (add to `mcp_server/requirements.txt`)
- `httpx>=0.24.0` (already in requirements.txt)

**Non-Blocking:**
- `JINA_API_KEY` (optional, for higher rate limits)
- Status summarizer (can be added later)

### Key Files to Modify

**Files to Create/Modify:**
- `mcp_server/tools.py` - Add `web_crawl_tool_handler`, `_is_valid_url`, `_crawl4ai_fetch`, `_jina_reader_fetch`, `web_crawl_tool`
- `mcp_server/requirements.txt` - Add `crawl4ai>=0.3.0`
- `mcp_server/config.py` - Add `JINA_API_KEY` (optional)
- `mcp_server/server.py` - Register web_crawl_tool
- `mcp_server/tests/test_web_crawl_tool.py` - Unit tests (create new)
- `backend/api/status_summarizers.py` - Add `summarize_web_crawl_result`
- `backend/api/mcp_client.py` - Add start status emission for web_crawl
- `env.example` - Add `JINA_API_KEY` with description

**Reference Files:**
- `.bmad-ephemeral/stories/tech-spec-epic-15.md` - Epic 15 technical specification
- `docs/epics/epic-15-extended-mcp-tools.md` - Epic overview
- `mcp_server/tools.py` - Existing tool patterns (store_memory, health_check)
- `backend/api/status_summarizers.py` - Existing summarizer patterns

### Testing Strategy

**Unit Tests:**
- Mock crawl4ai responses using MagicMock
- Mock Jina Reader responses using httpx mock
- Test fallback trigger conditions (crawl4ai exception -> Jina)
- Test all parameter handling (wait_for_js, max_length, include_images)
- Test content truncation at boundary

**Integration Tests (skippable):**
- Live crawl of test URL (e.g., httpbin.org)
- E2E via chat endpoint (requires full stack)

**Coverage Requirements:**
- >80% line coverage on web_crawl related code
- 100% coverage on error handling paths
- 100% coverage on fallback logic

### Success Metrics

| Metric | Target |
|--------|--------|
| Latency P95 | <5s |
| Success rate | >98% |
| Cost | Free (both providers) |
| Coverage | >80% |

### Potential Issues

1. **Docker Compatibility**: crawl4ai may need Playwright browser dependencies. May need to update Dockerfile:
   ```dockerfile
   RUN playwright install chromium --with-deps
   ```

2. **Memory Usage**: Playwright/crawl4ai can be memory-intensive. Monitor container memory.

3. **Blocked Sites**: Some sites aggressively block crawlers. Jina Reader usually works better for these.

---

## References

1. **Epic 15 Technical Specification** (`.bmad-ephemeral/stories/tech-spec-epic-15.md`)
   - AC 15.2.1-15.2.9 acceptance criteria
   - Data models and contracts

2. **Epic 15 Overview** (`docs/epics/epic-15-extended-mcp-tools.md`)
   - Story 15.2 details and schema
   - Architecture diagram

3. **crawl4ai Documentation** (`https://github.com/unclecode/crawl4ai`)
   - AsyncWebCrawler usage
   - JavaScript rendering options

4. **Jina Reader Documentation** (`https://jina.ai/reader`)
   - API endpoint usage
   - Free tier limits

5. **Existing Tool Patterns** (`mcp_server/tools.py`)
   - store_memory_tool_handler for async handler pattern
   - health_check_tool for simple tool pattern

6. **Status Summarizer Patterns** (`backend/api/status_summarizers.py`)
   - Existing summarizers for reference
   - SUMMARIZERS registry pattern

---

**Created:** 2025-12-30
**Epic:** Epic 15 - Extended MCP Tools - Web & Profile
**Story:** 15.2 - Web Crawl Tool (crawl4ai + Jina Fallback)
**Status:** done
**Tech Spec Ref:** AC #15.2.1-15.2.9
