"""
Unit tests for web_search MCP tool

Story 15.1: Web Search Tool (Tavily + DuckDuckGo)
- Tests Tavily API integration
- Tests DuckDuckGo fallback mechanism
- Tests parameter handling (search_depth, domains, max_results)
- Tests error scenarios (rate limit, timeout, network error)
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
import httpx

from mcp_server.tools import (
    web_search_tool_handler,
    web_search_tool,
    _tavily_search,
    _duckduckgo_search
)


class TestTavilySearch:
    """Test _tavily_search function."""

    @pytest.mark.asyncio
    async def test_tavily_search_success(self):
        """Test successful Tavily search."""
        mock_tavily_response = {
            "results": [
                {
                    "title": "Test Result 1",
                    "url": "https://example.com/1",
                    "content": "First test result content",
                    "score": 0.95
                },
                {
                    "title": "Test Result 2",
                    "url": "https://example.com/2",
                    "content": "Second test result content",
                    "score": 0.87
                }
            ]
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_tavily_response
        mock_response.raise_for_status = Mock()

        with patch('mcp_server.tools.web_search.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await _tavily_search(
                query="test query",
                max_results=5,
                search_depth="basic",
                include_domains=[],
                exclude_domains=[],
                api_key="test-key"
            )

            assert result["status"] == "success"
            assert result["provider"] == "tavily"
            assert result["query"] == "test query"
            assert len(result["results"]) == 2
            assert result["results"][0]["title"] == "Test Result 1"
            assert result["results"][0]["score"] == 0.95

    @pytest.mark.asyncio
    async def test_tavily_search_rate_limit(self):
        """Test 429 rate limit response."""
        mock_response = Mock()
        mock_response.status_code = 429

        with patch('mcp_server.tools.web_search.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await _tavily_search(
                query="test",
                max_results=5,
                search_depth="basic",
                include_domains=[],
                exclude_domains=[],
                api_key="test-key"
            )

            assert result["status"] == "error"
            assert result["provider"] == "tavily"
            assert result["error_code"] == "RATE_LIMIT"

    @pytest.mark.asyncio
    async def test_tavily_search_server_error(self):
        """Test 5xx server error response."""
        mock_response = Mock()
        mock_response.status_code = 503

        with patch('mcp_server.tools.web_search.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await _tavily_search(
                query="test",
                max_results=5,
                search_depth="basic",
                include_domains=[],
                exclude_domains=[],
                api_key="test-key"
            )

            assert result["status"] == "error"
            assert result["provider"] == "tavily"
            assert result["error_code"] == "SERVER_ERROR"

    @pytest.mark.asyncio
    async def test_tavily_search_timeout(self):
        """Test timeout handling."""
        with patch('mcp_server.tools.web_search.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_client_class.return_value = mock_client

            result = await _tavily_search(
                query="test",
                max_results=5,
                search_depth="basic",
                include_domains=[],
                exclude_domains=[],
                api_key="test-key"
            )

            assert result["status"] == "error"
            assert result["provider"] == "tavily"
            assert result["error_code"] == "TIMEOUT"

    @pytest.mark.asyncio
    async def test_tavily_search_uses_10s_timeout(self):
        """Test that Tavily uses 10s timeout."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = Mock()

        with patch('mcp_server.tools.web_search.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await _tavily_search(
                query="test",
                max_results=5,
                search_depth="basic",
                include_domains=[],
                exclude_domains=[],
                api_key="test-key"
            )

            # Check that AsyncClient was called with timeout=10.0
            mock_client_class.assert_called_once_with(timeout=10.0)


class TestDuckDuckGoSearch:
    """Test _duckduckgo_search function."""

    @pytest.mark.asyncio
    async def test_duckduckgo_search_success(self):
        """Test successful DuckDuckGo search."""
        mock_ddg_results = [
            {"title": "DDG Result 1", "href": "https://ddg.com/1", "body": "DDG content 1"},
            {"title": "DDG Result 2", "href": "https://ddg.com/2", "body": "DDG content 2"}
        ]

        with patch('duckduckgo_search.DDGS') as mock_ddgs_class:
            mock_ddgs = Mock()
            mock_ddgs.text.return_value = mock_ddg_results
            mock_ddgs_class.return_value = mock_ddgs

            result = await _duckduckgo_search(query="test query", max_results=5)

            assert result["status"] == "success"
            assert result["provider"] == "duckduckgo"
            assert result["query"] == "test query"
            assert len(result["results"]) == 2
            assert result["results"][0]["title"] == "DDG Result 1"
            assert result["results"][0]["url"] == "https://ddg.com/1"
            assert result["results"][0]["snippet"] == "DDG content 1"
            assert result["results"][0]["score"] is None  # DDG doesn't provide scores

    @pytest.mark.asyncio
    async def test_duckduckgo_search_failure(self):
        """Test DuckDuckGo search failure handling."""
        with patch('duckduckgo_search.DDGS') as mock_ddgs_class:
            mock_ddgs_class.side_effect = Exception("DDG error")

            result = await _duckduckgo_search(query="test", max_results=5)

            assert result["status"] == "error"
            assert result["provider"] == "duckduckgo"
            assert "error_message" in result
            assert result["results"] == []


class TestWebSearchToolHandler:
    """Test web_search_tool_handler function."""

    @pytest.fixture
    def mock_tavily_response(self):
        """Standard Tavily success response."""
        return {
            "results": [
                {
                    "title": "Test Result 1",
                    "url": "https://example.com/1",
                    "content": "First test result content",
                    "score": 0.95
                },
                {
                    "title": "Test Result 2",
                    "url": "https://example.com/2",
                    "content": "Second test result content",
                    "score": 0.87
                }
            ]
        }

    @pytest.mark.asyncio
    async def test_tavily_search_success(self, mock_tavily_response):
        """Test successful Tavily search via handler."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_tavily_response
        mock_response.raise_for_status = Mock()

        with patch('mcp_server.tools.web_search.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.web_search.get_config') as mock_config:
                mock_config.return_value = {"TAVILY_API_KEY": "test-key"}

                result = await web_search_tool_handler(query="test query")

                assert result["status"] == "success"
                assert result["provider"] == "tavily"
                assert len(result["results"]) == 2
                assert result["results"][0]["title"] == "Test Result 1"

    @pytest.mark.asyncio
    async def test_fallback_to_duckduckgo_on_tavily_failure(self):
        """Test DuckDuckGo fallback when Tavily fails."""
        # Mock Tavily to raise an exception
        with patch('mcp_server.tools.web_search.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(side_effect=Exception("Tavily unavailable"))
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.web_search.get_config') as mock_config:
                mock_config.return_value = {"TAVILY_API_KEY": "test-key"}

                with patch('duckduckgo_search.DDGS') as mock_ddgs_class:
                    mock_ddgs = Mock()
                    mock_ddgs.text.return_value = [
                        {"title": "DDG Result", "href": "https://ddg.com", "body": "DDG content"}
                    ]
                    mock_ddgs_class.return_value = mock_ddgs

                    result = await web_search_tool_handler(query="test query")

                    assert result["status"] == "success"
                    assert result["provider"] == "duckduckgo"

    @pytest.mark.asyncio
    async def test_rate_limit_triggers_fallback(self):
        """Test 429 rate limit triggers DuckDuckGo fallback."""
        mock_response = Mock()
        mock_response.status_code = 429

        with patch('mcp_server.tools.web_search.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.web_search.get_config') as mock_config:
                mock_config.return_value = {"TAVILY_API_KEY": "test-key"}

                with patch('duckduckgo_search.DDGS') as mock_ddgs_class:
                    mock_ddgs = Mock()
                    mock_ddgs.text.return_value = []
                    mock_ddgs_class.return_value = mock_ddgs

                    result = await web_search_tool_handler(query="test")

                    assert result["provider"] == "duckduckgo"

    @pytest.mark.asyncio
    async def test_timeout_triggers_fallback(self):
        """Test timeout triggers DuckDuckGo fallback."""
        with patch('mcp_server.tools.web_search.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.web_search.get_config') as mock_config:
                mock_config.return_value = {"TAVILY_API_KEY": "test-key"}

                with patch('duckduckgo_search.DDGS') as mock_ddgs_class:
                    mock_ddgs = Mock()
                    mock_ddgs.text.return_value = []
                    mock_ddgs_class.return_value = mock_ddgs

                    result = await web_search_tool_handler(query="test")

                    assert result["provider"] == "duckduckgo"

    @pytest.mark.asyncio
    async def test_server_error_triggers_fallback(self):
        """Test 5xx server error triggers DuckDuckGo fallback."""
        mock_response = Mock()
        mock_response.status_code = 500

        with patch('mcp_server.tools.web_search.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.web_search.get_config') as mock_config:
                mock_config.return_value = {"TAVILY_API_KEY": "test-key"}

                with patch('duckduckgo_search.DDGS') as mock_ddgs_class:
                    mock_ddgs = Mock()
                    mock_ddgs.text.return_value = []
                    mock_ddgs_class.return_value = mock_ddgs

                    result = await web_search_tool_handler(query="test")

                    assert result["provider"] == "duckduckgo"

    @pytest.mark.asyncio
    async def test_search_depth_parameter(self, mock_tavily_response):
        """Test search_depth parameter passed correctly."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_tavily_response
        mock_response.raise_for_status = Mock()

        with patch('mcp_server.tools.web_search.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.web_search.get_config') as mock_config:
                mock_config.return_value = {"TAVILY_API_KEY": "test-key"}

                await web_search_tool_handler(
                    query="test",
                    search_depth="advanced"
                )

                call_args = mock_client.post.call_args
                payload = call_args[1]["json"]
                assert payload["search_depth"] == "advanced"

    @pytest.mark.asyncio
    async def test_invalid_search_depth_defaults_to_basic(self, mock_tavily_response):
        """Test invalid search_depth defaults to 'basic'."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_tavily_response
        mock_response.raise_for_status = Mock()

        with patch('mcp_server.tools.web_search.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.web_search.get_config') as mock_config:
                mock_config.return_value = {"TAVILY_API_KEY": "test-key"}

                await web_search_tool_handler(
                    query="test",
                    search_depth="invalid"  # Invalid value
                )

                call_args = mock_client.post.call_args
                payload = call_args[1]["json"]
                assert payload["search_depth"] == "basic"

    @pytest.mark.asyncio
    async def test_domain_filtering(self, mock_tavily_response):
        """Test domain filtering parameters."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_tavily_response
        mock_response.raise_for_status = Mock()

        with patch('mcp_server.tools.web_search.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.web_search.get_config') as mock_config:
                mock_config.return_value = {"TAVILY_API_KEY": "test-key"}

                await web_search_tool_handler(
                    query="test",
                    include_domains=["example.com"],
                    exclude_domains=["spam.com"]
                )

                call_args = mock_client.post.call_args
                payload = call_args[1]["json"]
                assert payload["include_domains"] == ["example.com"]
                assert payload["exclude_domains"] == ["spam.com"]

    @pytest.mark.asyncio
    async def test_max_results_capped_at_10(self, mock_tavily_response):
        """Test max_results is capped at 10."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_tavily_response
        mock_response.raise_for_status = Mock()

        with patch('mcp_server.tools.web_search.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.web_search.get_config') as mock_config:
                mock_config.return_value = {"TAVILY_API_KEY": "test-key"}

                await web_search_tool_handler(
                    query="test",
                    max_results=50  # Over limit
                )

                call_args = mock_client.post.call_args
                payload = call_args[1]["json"]
                assert payload["max_results"] == 10  # Capped

    @pytest.mark.asyncio
    async def test_max_results_minimum_is_1(self, mock_tavily_response):
        """Test max_results is at least 1."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_tavily_response
        mock_response.raise_for_status = Mock()

        with patch('mcp_server.tools.web_search.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.web_search.get_config') as mock_config:
                mock_config.return_value = {"TAVILY_API_KEY": "test-key"}

                await web_search_tool_handler(
                    query="test",
                    max_results=0  # Below minimum
                )

                call_args = mock_client.post.call_args
                payload = call_args[1]["json"]
                assert payload["max_results"] == 1  # Minimum

    @pytest.mark.asyncio
    async def test_default_max_results_is_5(self, mock_tavily_response):
        """Test default max_results is 5."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_tavily_response
        mock_response.raise_for_status = Mock()

        with patch('mcp_server.tools.web_search.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.web_search.get_config') as mock_config:
                mock_config.return_value = {"TAVILY_API_KEY": "test-key"}

                await web_search_tool_handler(query="test")

                call_args = mock_client.post.call_args
                payload = call_args[1]["json"]
                assert payload["max_results"] == 5

    @pytest.mark.asyncio
    async def test_no_api_key_uses_duckduckgo(self):
        """Test missing API key goes directly to DuckDuckGo."""
        with patch('mcp_server.tools.web_search.get_config') as mock_config:
            mock_config.return_value = {}  # No API key

            with patch('duckduckgo_search.DDGS') as mock_ddgs_class:
                mock_ddgs = Mock()
                mock_ddgs.text.return_value = []
                mock_ddgs_class.return_value = mock_ddgs

                result = await web_search_tool_handler(query="test")

                assert result["provider"] == "duckduckgo"

    @pytest.mark.asyncio
    async def test_empty_api_key_uses_duckduckgo(self):
        """Test empty string API key goes directly to DuckDuckGo."""
        with patch('mcp_server.tools.web_search.get_config') as mock_config:
            mock_config.return_value = {"TAVILY_API_KEY": ""}  # Empty key

            with patch('duckduckgo_search.DDGS') as mock_ddgs_class:
                mock_ddgs = Mock()
                mock_ddgs.text.return_value = []
                mock_ddgs_class.return_value = mock_ddgs

                result = await web_search_tool_handler(query="test")

                assert result["provider"] == "duckduckgo"

    @pytest.mark.asyncio
    async def test_none_domains_default_to_empty_list(self, mock_tavily_response):
        """Test None domains default to empty lists."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_tavily_response
        mock_response.raise_for_status = Mock()

        with patch('mcp_server.tools.web_search.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.web_search.get_config') as mock_config:
                mock_config.return_value = {"TAVILY_API_KEY": "test-key"}

                await web_search_tool_handler(
                    query="test",
                    include_domains=None,
                    exclude_domains=None
                )

                call_args = mock_client.post.call_args
                payload = call_args[1]["json"]
                assert payload["include_domains"] == []
                assert payload["exclude_domains"] == []


class TestWebSearchToolSchema:
    """Test web_search tool schema definition."""

    def test_tool_schema_structure(self):
        """Verify tool schema has required fields."""
        assert web_search_tool["name"] == "web_search"
        assert "description" in web_search_tool
        assert "inputSchema" in web_search_tool
        assert "handler" in web_search_tool

    def test_input_schema_properties(self):
        """Verify input schema has all expected properties."""
        schema = web_search_tool["inputSchema"]
        props = schema["properties"]

        assert "query" in props
        assert "max_results" in props
        assert "search_depth" in props
        assert "include_domains" in props
        assert "exclude_domains" in props

    def test_required_fields(self):
        """Verify only query is required."""
        schema = web_search_tool["inputSchema"]
        assert schema["required"] == ["query"]

    def test_max_results_schema(self):
        """Test max_results has correct schema."""
        props = web_search_tool["inputSchema"]["properties"]
        max_results = props["max_results"]

        assert max_results["type"] == "integer"
        assert max_results["default"] == 5
        assert max_results["minimum"] == 1
        assert max_results["maximum"] == 10

    def test_search_depth_schema(self):
        """Test search_depth has correct enum."""
        props = web_search_tool["inputSchema"]["properties"]
        search_depth = props["search_depth"]

        assert search_depth["type"] == "string"
        assert search_depth["enum"] == ["basic", "advanced"]
        assert search_depth["default"] == "basic"

    def test_domain_arrays_schema(self):
        """Test domain arrays have correct schema."""
        props = web_search_tool["inputSchema"]["properties"]

        assert props["include_domains"]["type"] == "array"
        assert props["include_domains"]["items"]["type"] == "string"

        assert props["exclude_domains"]["type"] == "array"
        assert props["exclude_domains"]["items"]["type"] == "string"

    def test_handler_is_callable(self):
        """Test handler is callable and correct."""
        assert callable(web_search_tool["handler"])
        assert web_search_tool["handler"] == web_search_tool_handler

    def test_description_mentions_providers(self):
        """Test description mentions both providers."""
        desc = web_search_tool["description"]
        assert "Tavily" in desc
        assert "DuckDuckGo" in desc
