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

# Import the functions to test
from mcp_server.tools import (
    web_crawl_tool_handler,
    _is_valid_url,
    _crawl4ai_fetch,
    _jina_reader_fetch,
)


# ============ Fixtures ============

@pytest.fixture
def mock_crawl4ai_result():
    """Mock crawl4ai result with standard webpage content."""
    result = MagicMock()
    result.success = True
    result.markdown = "# Page Title\n\nThis is the page content with some text."
    result.metadata = {
        "title": "Page Title",
        "description": "A test page description",
        "author": "Test Author",
        "published_date": "2025-01-15",
        "content_type": "text/html"
    }
    result.links = {"internal": [{"href": "/link1"}], "external": [{"href": "https://example.com"}]}
    result.html = "<html><body>content</body></html>"
    return result


@pytest.fixture
def mock_crawl4ai_empty_result():
    """Mock crawl4ai result for empty content."""
    result = MagicMock()
    result.success = True
    result.markdown = ""
    result.metadata = {"title": "", "content_type": "text/html"}
    result.links = {"internal": [], "external": []}
    result.html = None
    return result


@pytest.fixture
def mock_crawl4ai_failed_result():
    """Mock crawl4ai result for failed crawl."""
    result = MagicMock()
    result.success = False
    result.error_message = "Connection refused"
    return result


@pytest.fixture
def mock_jina_response():
    """Mock httpx response for Jina Reader success."""
    response = MagicMock()
    response.status_code = 200
    response.text = "# Jina Title\n\nContent from Jina Reader."
    return response


@pytest.fixture
def mock_jina_error_response():
    """Mock httpx response for Jina Reader error."""
    response = MagicMock()
    response.status_code = 503
    response.text = "Service Unavailable"
    return response


# ============ URL Validation Tests ============

class TestUrlValidation:
    """Test _is_valid_url function."""

    def test_valid_https_url(self):
        assert _is_valid_url("https://example.com/page") is True

    def test_valid_http_url(self):
        assert _is_valid_url("http://example.com/page") is True

    def test_valid_url_with_port(self):
        assert _is_valid_url("https://example.com:8080/page") is True

    def test_valid_url_with_query(self):
        assert _is_valid_url("https://example.com/page?q=test&lang=en") is True

    def test_valid_url_with_fragment(self):
        assert _is_valid_url("https://example.com/page#section") is True

    def test_invalid_ftp_url(self):
        assert _is_valid_url("ftp://example.com/file") is False

    def test_invalid_no_scheme(self):
        assert _is_valid_url("example.com/page") is False

    def test_invalid_javascript_scheme(self):
        assert _is_valid_url("javascript:alert(1)") is False

    def test_invalid_file_scheme(self):
        assert _is_valid_url("file:///etc/passwd") is False

    def test_invalid_localhost(self):
        assert _is_valid_url("http://localhost/page") is False

    def test_invalid_127_0_0_1(self):
        assert _is_valid_url("http://127.0.0.1/page") is False

    def test_invalid_0_0_0_0(self):
        assert _is_valid_url("http://0.0.0.0/page") is False

    def test_invalid_ipv6_localhost(self):
        assert _is_valid_url("http://[::1]/page") is False

    def test_invalid_private_ip_10(self):
        assert _is_valid_url("http://10.0.0.1/page") is False

    def test_invalid_private_ip_10_subnet(self):
        assert _is_valid_url("http://10.255.255.255/page") is False

    def test_invalid_private_ip_192(self):
        assert _is_valid_url("http://192.168.1.1/page") is False

    def test_invalid_private_ip_172_16(self):
        assert _is_valid_url("http://172.16.0.1/page") is False

    def test_invalid_private_ip_172_31(self):
        assert _is_valid_url("http://172.31.255.255/page") is False

    def test_valid_ip_172_15(self):
        """172.15.x.x is NOT private."""
        assert _is_valid_url("http://172.15.0.1/page") is True

    def test_valid_ip_172_32(self):
        """172.32.x.x is NOT private."""
        assert _is_valid_url("http://172.32.0.1/page") is True

    def test_invalid_link_local(self):
        assert _is_valid_url("http://169.254.0.1/page") is False

    def test_invalid_empty_string(self):
        assert _is_valid_url("") is False

    def test_invalid_malformed(self):
        assert _is_valid_url("not a url") is False

    def test_invalid_none(self):
        # Should handle None gracefully (returns False)
        assert _is_valid_url(None) is False  # type: ignore


# ============ crawl4ai Tests ============

class TestCrawl4aiFetch:
    """Test crawl4ai primary provider."""

    @pytest.mark.asyncio
    async def test_crawl4ai_success(self, mock_crawl4ai_result):
        """Test successful crawl4ai fetch."""
        with patch("crawl4ai.AsyncWebCrawler") as mock_crawler_class:
            mock_crawler = AsyncMock()
            mock_crawler.arun.return_value = mock_crawl4ai_result
            mock_crawler_class.return_value.__aenter__.return_value = mock_crawler
            mock_crawler_class.return_value.__aexit__.return_value = None

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
            assert result["metadata"]["links_count"] == 2

    @pytest.mark.asyncio
    async def test_crawl4ai_truncation(self, mock_crawl4ai_result):
        """Test content truncation at max_length."""
        mock_crawl4ai_result.markdown = "A" * 20000  # Long content

        with patch("crawl4ai.AsyncWebCrawler") as mock_crawler_class:
            mock_crawler = AsyncMock()
            mock_crawler.arun.return_value = mock_crawl4ai_result
            mock_crawler_class.return_value.__aenter__.return_value = mock_crawler
            mock_crawler_class.return_value.__aexit__.return_value = None

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
    async def test_crawl4ai_empty_content(self, mock_crawl4ai_empty_result):
        """Test handling of empty content (no HTML either)."""
        with patch("crawl4ai.AsyncWebCrawler") as mock_crawler_class:
            mock_crawler = AsyncMock()
            mock_crawler.arun.return_value = mock_crawl4ai_empty_result
            mock_crawler_class.return_value.__aenter__.return_value = mock_crawler
            mock_crawler_class.return_value.__aexit__.return_value = None

            result = await _crawl4ai_fetch(
                url="https://example.com/empty",
                include_images=False,
                max_length=10000,
                wait_for_js=False,
                request_id="test123"
            )

            assert result["status"] == "error"
            assert "No content extracted" in result["error_message"]

    @pytest.mark.asyncio
    async def test_crawl4ai_failed_crawl(self, mock_crawl4ai_failed_result):
        """Test handling of failed crawl."""
        with patch("crawl4ai.AsyncWebCrawler") as mock_crawler_class:
            mock_crawler = AsyncMock()
            mock_crawler.arun.return_value = mock_crawl4ai_failed_result
            mock_crawler_class.return_value.__aenter__.return_value = mock_crawler
            mock_crawler_class.return_value.__aexit__.return_value = None

            with pytest.raises(Exception) as exc_info:
                await _crawl4ai_fetch(
                    url="https://example.com",
                    include_images=False,
                    max_length=10000,
                    wait_for_js=False,
                    request_id="test123"
                )

            assert "Crawl failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_crawl4ai_import_error(self):
        """Test handling when crawl4ai is not installed."""
        # Lazy import test - when crawl4ai module is not available,
        # the function raises ImportError which triggers fallback to Jina
        # This is tested via the handler fallback tests
        pass  # Skip - import is handled at function level

    @pytest.mark.asyncio
    async def test_crawl4ai_title_extraction(self, mock_crawl4ai_result):
        """Test title extraction from markdown when metadata is empty."""
        mock_crawl4ai_result.metadata = {}  # No metadata

        with patch("crawl4ai.AsyncWebCrawler") as mock_crawler_class:
            mock_crawler = AsyncMock()
            mock_crawler.arun.return_value = mock_crawl4ai_result
            mock_crawler_class.return_value.__aenter__.return_value = mock_crawler
            mock_crawler_class.return_value.__aexit__.return_value = None

            result = await _crawl4ai_fetch(
                url="https://example.com",
                include_images=False,
                max_length=10000,
                wait_for_js=False,
                request_id="test123"
            )

            # Title should be extracted from markdown heading
            assert result["title"] == "Page Title"


# ============ Jina Reader Fallback Tests ============

class TestJinaReaderFetch:
    """Test Jina Reader fallback provider."""

    @pytest.mark.asyncio
    async def test_jina_success(self, mock_jina_response):
        """Test successful Jina Reader fetch."""
        with patch("mcp_server.tools.web_crawl.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_jina_response
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client_class.return_value.__aexit__.return_value = None

            with patch("mcp_server.tools.web_crawl.get_config") as mock_config:
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

        with patch("mcp_server.tools.web_crawl.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client_class.return_value.__aexit__.return_value = None

            with patch("mcp_server.tools.web_crawl.get_config") as mock_config:
                mock_config.return_value = {}

                result = await _jina_reader_fetch(
                    url="https://example.com",
                    max_length=5000,
                    request_id="test123"
                )

                assert len(result["content"]) == 5000
                assert result["truncated"] is True

    @pytest.mark.asyncio
    async def test_jina_http_error(self, mock_jina_error_response):
        """Test Jina Reader HTTP error handling."""
        with patch("mcp_server.tools.web_crawl.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_jina_error_response
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client_class.return_value.__aexit__.return_value = None

            with patch("mcp_server.tools.web_crawl.get_config") as mock_config:
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

        with patch("mcp_server.tools.web_crawl.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.TimeoutException("timeout")
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client_class.return_value.__aexit__.return_value = None

            with patch("mcp_server.tools.web_crawl.get_config") as mock_config:
                mock_config.return_value = {}

                result = await _jina_reader_fetch(
                    url="https://example.com",
                    max_length=10000,
                    request_id="test123"
                )

                assert result["status"] == "error"
                assert "timed out" in result["error_message"]

    @pytest.mark.asyncio
    async def test_jina_with_api_key(self, mock_jina_response):
        """Test Jina Reader with API key."""
        with patch("mcp_server.tools.web_crawl.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_jina_response
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client_class.return_value.__aexit__.return_value = None

            with patch("mcp_server.tools.web_crawl.get_config") as mock_config:
                mock_config.return_value = {"JINA_API_KEY": "test-key-123"}

                await _jina_reader_fetch(
                    url="https://example.com",
                    max_length=10000,
                    request_id="test123"
                )

                # Verify API key was used in headers
                call_kwargs = mock_client.get.call_args[1]
                assert "Authorization" in call_kwargs["headers"]
                assert "Bearer test-key-123" in call_kwargs["headers"]["Authorization"]


# ============ Integration: Fallback Tests ============

class TestWebCrawlFallback:
    """Test crawl4ai to Jina Reader fallback."""

    @pytest.mark.asyncio
    async def test_fallback_to_jina_on_crawl4ai_failure(self, mock_jina_response):
        """Test fallback to Jina when crawl4ai fails."""
        with patch("mcp_server.tools.web_crawl._crawl4ai_fetch") as mock_crawl4ai:
            mock_crawl4ai.side_effect = Exception("crawl4ai failed")

            with patch("mcp_server.tools.web_crawl._jina_reader_fetch") as mock_jina:
                mock_jina.return_value = {
                    "status": "success",
                    "provider": "jina",
                    "url": "https://example.com",
                    "title": "Fallback Title",
                    "content": "A" * 250,
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
    async def test_fallback_to_jina_on_crawl4ai_error_result(self):
        """Test fallback when crawl4ai returns error status."""
        with patch("mcp_server.tools.web_crawl._crawl4ai_fetch") as mock_crawl4ai:
            mock_crawl4ai.return_value = {
                "status": "error",
                "provider": "crawl4ai",
                "url": "https://example.com",
                "error_message": "Page blocked"
            }

            with patch("mcp_server.tools.web_crawl._jina_reader_fetch") as mock_jina:
                mock_jina.return_value = {
                    "status": "success",
                    "provider": "jina",
                    "url": "https://example.com",
                    "title": "Fallback Title",
                    "content": "A" * 250,
                    "metadata": {},
                    "truncated": False
                }

                result = await web_crawl_tool_handler(
                    url="https://example.com",
                    max_length=10000
                )

                assert result["status"] == "success"
                assert result["provider"] == "jina"

    @pytest.mark.asyncio
    async def test_both_providers_fail(self):
        """Test error when all providers fail."""
        with patch("mcp_server.tools.web_crawl._crawl4ai_fetch") as mock_crawl4ai:
            mock_crawl4ai.side_effect = Exception("crawl4ai failed")

            with patch("mcp_server.tools.web_crawl._jina_reader_fetch") as mock_jina:
                mock_jina.side_effect = Exception("jina failed")

                with patch("mcp_server.tools.web_crawl._browser_fetch") as mock_browser:
                    mock_browser.side_effect = Exception("browser failed")

                    result = await web_crawl_tool_handler(
                        url="https://example.com",
                        max_length=10000
                    )

                    assert result["status"] == "error"
                    assert result["provider"] is None
                    assert "All providers failed" in result["error_message"]

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

    @pytest.mark.asyncio
    async def test_private_ip_blocked(self):
        """Test that private IP URLs are blocked."""
        result = await web_crawl_tool_handler(
            url="http://192.168.1.1/admin",
            max_length=10000
        )

        assert result["status"] == "error"
        assert "Invalid URL" in result["error_message"]

    @pytest.mark.asyncio
    async def test_success_with_crawl4ai(self, mock_crawl4ai_result):
        """Test successful crawl without fallback."""
        with patch("mcp_server.tools.web_crawl._crawl4ai_fetch") as mock_crawl4ai:
            mock_crawl4ai.return_value = {
                "status": "success",
                "provider": "crawl4ai",
                "url": "https://example.com",
                "title": "Test Page",
                "content": "A" * 250,
                "metadata": {"links_count": 5},
                "truncated": False
            }

            result = await web_crawl_tool_handler(
                url="https://example.com",
                max_length=10000
            )

            assert result["status"] == "success"
            assert result["provider"] == "crawl4ai"
            assert result["title"] == "Test Page"


# ============ Parameter Tests ============

class TestWebCrawlParameters:
    """Test web_crawl tool parameters."""

    @pytest.mark.asyncio
    async def test_default_parameters(self):
        """Test default parameter values."""
        with patch("mcp_server.tools.web_crawl._crawl4ai_fetch") as mock_crawl4ai:
            mock_crawl4ai.return_value = {
                "status": "success",
                "provider": "crawl4ai",
                "url": "https://example.com",
                "title": "Test",
                "content": "Content",
                "metadata": {},
                "truncated": False
            }

            await web_crawl_tool_handler(url="https://example.com")

            # Handler calls _crawl4ai_fetch(url, include_images, max_length, wait_for_js, request_id)
            call_args = mock_crawl4ai.call_args[0]  # Positional args
            assert call_args[0] == "https://example.com"  # url
            assert call_args[1] is False  # include_images default
            assert call_args[2] == 10000  # max_length default
            assert call_args[3] is False  # wait_for_js default

    @pytest.mark.asyncio
    async def test_custom_max_length(self):
        """Test custom max_length parameter."""
        with patch("mcp_server.tools.web_crawl._crawl4ai_fetch") as mock_crawl4ai:
            mock_crawl4ai.return_value = {
                "status": "success",
                "provider": "crawl4ai",
                "url": "https://example.com",
                "title": "Test",
                "content": "Content",
                "metadata": {},
                "truncated": False
            }

            await web_crawl_tool_handler(
                url="https://example.com",
                max_length=5000
            )

            # Handler calls _crawl4ai_fetch(url, include_images, max_length, wait_for_js, request_id)
            call_args = mock_crawl4ai.call_args[0]  # Positional args
            assert call_args[2] == 5000  # max_length

    @pytest.mark.asyncio
    async def test_wait_for_js_parameter(self):
        """Test wait_for_js parameter."""
        with patch("mcp_server.tools.web_crawl._crawl4ai_fetch") as mock_crawl4ai:
            mock_crawl4ai.return_value = {
                "status": "success",
                "provider": "crawl4ai",
                "url": "https://example.com",
                "title": "Test",
                "content": "Content",
                "metadata": {},
                "truncated": False
            }

            await web_crawl_tool_handler(
                url="https://example.com",
                wait_for_js=True
            )

            # Handler calls _crawl4ai_fetch(url, include_images, max_length, wait_for_js, request_id)
            call_args = mock_crawl4ai.call_args[0]  # Positional args
            assert call_args[3] is True  # wait_for_js
