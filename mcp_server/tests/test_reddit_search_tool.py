"""
Unit tests for reddit_search MCP tool

Story 15.3: Reddit Search Tool (PRAW + JSON API)
- Tests PRAW primary provider with mocked Reddit client
- Tests JSON API fallback when PRAW unavailable or fails
- Tests all parameters: query, subreddit, sort, time_filter, limit, include_comments
- Tests error handling for private subreddits, rate limiting, timeouts
- Tests fallback trigger conditions
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock

import httpx

from mcp_server.tools import (
    reddit_search_tool_handler,
    reddit_search_tool,
    _praw_search_sync,
    _reddit_json_search,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_praw_submission():
    """Create a mock PRAW submission object."""
    submission = MagicMock()
    submission.title = "Test Post Title"
    submission.subreddit.display_name = "testsubreddit"
    submission.author = MagicMock()
    submission.author.name = "testuser"
    submission.score = 100
    submission.permalink = "/r/testsubreddit/comments/abc123/test_post"
    submission.selftext = "This is the post content. " * 20  # ~400 chars
    submission.num_comments = 15
    submission.created_utc = 1704067200.0  # 2024-01-01

    # Mock comments
    submission.comments = MagicMock()
    submission.comments.replace_more = MagicMock()

    mock_comment = MagicMock()
    mock_comment.author = MagicMock()
    mock_comment.author.name = "commenter1"
    mock_comment.score = 50
    mock_comment.body = "This is a great comment! " * 10  # ~250 chars
    mock_comment.replies = []

    submission.comments.__iter__ = lambda self: iter([mock_comment])
    submission.comments.__getitem__ = lambda self, idx: [mock_comment][idx] if idx < 1 else None

    return submission


@pytest.fixture
def mock_praw_comment():
    """Create a mock PRAW comment object."""
    comment = MagicMock()
    comment.author = MagicMock()
    comment.author.name = "commenter1"
    comment.score = 50
    comment.body = "This is a test comment body. " * 10
    comment.replies = []
    return comment


@pytest.fixture
def mock_json_api_response():
    """Create a mock Reddit JSON API response."""
    return {
        "data": {
            "children": [
                {
                    "data": {
                        "title": "JSON API Post Title",
                        "subreddit": "python",
                        "author": "jsonuser",
                        "score": 200,
                        "permalink": "/r/python/comments/xyz789/json_api_post",
                        "selftext": "Post content from JSON API",
                        "num_comments": 25,
                        "created_utc": 1704067200.0
                    }
                },
                {
                    "data": {
                        "title": "Second Post",
                        "subreddit": "python",
                        "author": "anotheruser",
                        "score": 150,
                        "permalink": "/r/python/comments/def456/second_post",
                        "selftext": "Another post content",
                        "num_comments": 10,
                        "created_utc": 1704153600.0
                    }
                }
            ]
        }
    }


@pytest.fixture
def mock_config_with_reddit():
    """Mock config with Reddit credentials."""
    return {
        "REDDIT_CLIENT_ID": "test_client_id",
        "REDDIT_CLIENT_SECRET": "test_client_secret",
        "REDDIT_USER_AGENT": "annie-bot/1.0 test"
    }


@pytest.fixture
def mock_config_without_reddit():
    """Mock config without Reddit credentials."""
    return {
        "REDDIT_USER_AGENT": "annie-bot/1.0 test"
    }


# =============================================================================
# Test Tool Schema
# =============================================================================

class TestRedditSearchToolSchema:
    """Test reddit_search tool schema definition."""

    def test_tool_name(self):
        """Test tool name is correct."""
        assert reddit_search_tool["name"] == "reddit_search"

    def test_tool_has_description(self):
        """Test tool has description."""
        assert "description" in reddit_search_tool
        assert len(reddit_search_tool["description"]) > 50

    def test_tool_has_input_schema(self):
        """Test tool has input schema."""
        assert "inputSchema" in reddit_search_tool
        schema = reddit_search_tool["inputSchema"]
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema

    def test_required_parameters(self):
        """Test required parameters."""
        required = reddit_search_tool["inputSchema"]["required"]
        assert "query" in required

    def test_all_parameters_defined(self):
        """Test all parameters are defined."""
        props = reddit_search_tool["inputSchema"]["properties"]
        expected_params = [
            "query", "subreddit", "search_type", "sort",
            "time_filter", "limit", "include_comments"
        ]
        for param in expected_params:
            assert param in props, f"Missing parameter: {param}"

    def test_sort_options(self):
        """Test sort parameter has correct options."""
        sort_prop = reddit_search_tool["inputSchema"]["properties"]["sort"]
        assert sort_prop["enum"] == ["relevance", "hot", "top", "new"]
        assert sort_prop["default"] == "relevance"

    def test_time_filter_options(self):
        """Test time_filter parameter has correct options."""
        tf_prop = reddit_search_tool["inputSchema"]["properties"]["time_filter"]
        assert tf_prop["enum"] == ["hour", "day", "week", "month", "year", "all"]
        assert tf_prop["default"] == "all"

    def test_limit_constraints(self):
        """Test limit parameter has correct constraints."""
        limit_prop = reddit_search_tool["inputSchema"]["properties"]["limit"]
        assert limit_prop["minimum"] == 1
        assert limit_prop["maximum"] == 25
        assert limit_prop["default"] == 10


# =============================================================================
# Test Parameter Validation
# =============================================================================

class TestParameterValidation:
    """Test parameter validation in reddit_search_tool_handler."""

    @pytest.mark.asyncio
    async def test_empty_query_returns_error(self):
        """Test that empty query returns validation error."""
        with patch('mcp_server.tools.reddit_search.get_config', return_value={}):
            result = await reddit_search_tool_handler(query="")
            assert result["status"] == "error"
            assert result["error_code"] == "VALIDATION_ERROR"
            assert "Query is required" in result["error_message"]

    @pytest.mark.asyncio
    async def test_whitespace_query_returns_error(self):
        """Test that whitespace-only query returns validation error."""
        with patch('mcp_server.tools.reddit_search.get_config', return_value={}):
            result = await reddit_search_tool_handler(query="   ")
            assert result["status"] == "error"
            assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_invalid_sort_returns_error(self):
        """Test that invalid sort option returns validation error."""
        with patch('mcp_server.tools.reddit_search.get_config', return_value={}):
            result = await reddit_search_tool_handler(query="test", sort="invalid")
            assert result["status"] == "error"
            assert result["error_code"] == "VALIDATION_ERROR"
            assert "Invalid sort option" in result["error_message"]

    @pytest.mark.asyncio
    async def test_invalid_time_filter_returns_error(self):
        """Test that invalid time_filter returns validation error."""
        with patch('mcp_server.tools.reddit_search.get_config', return_value={}):
            result = await reddit_search_tool_handler(query="test", time_filter="invalid")
            assert result["status"] == "error"
            assert result["error_code"] == "VALIDATION_ERROR"
            assert "Invalid time_filter" in result["error_message"]

    @pytest.mark.asyncio
    async def test_limit_clamped_to_minimum(self):
        """Test that limit below minimum is clamped to 1."""
        with patch('mcp_server.tools.reddit_search.get_config', return_value={}):
            with patch('mcp_server.tools.reddit_search._reddit_json_search', new_callable=AsyncMock) as mock_search:
                mock_search.return_value = {"status": "success", "results": [], "query": "test", "subreddit": "all"}
                await reddit_search_tool_handler(query="test", limit=0)
                # Verify limit was clamped to 1
                call_args = mock_search.call_args
                assert call_args[1]["limit"] == 1

    @pytest.mark.asyncio
    async def test_limit_clamped_to_maximum(self):
        """Test that limit above maximum is clamped to 25."""
        with patch('mcp_server.tools.reddit_search.get_config', return_value={}):
            with patch('mcp_server.tools.reddit_search._reddit_json_search', new_callable=AsyncMock) as mock_search:
                mock_search.return_value = {"status": "success", "results": [], "query": "test", "subreddit": "all"}
                await reddit_search_tool_handler(query="test", limit=100)
                # Verify limit was clamped to 25
                call_args = mock_search.call_args
                assert call_args[1]["limit"] == 25


# =============================================================================
# Test PRAW Provider
# =============================================================================

class TestPRAWProvider:
    """Test PRAW primary provider."""

    def test_praw_search_success(self, mock_praw_submission, mock_config_with_reddit):
        """Test successful PRAW search."""
        with patch('praw.Reddit') as mock_reddit_class:
            mock_reddit = MagicMock()
            mock_reddit_class.return_value = mock_reddit
            mock_subreddit = MagicMock()
            mock_reddit.subreddit.return_value = mock_subreddit
            mock_subreddit.search.return_value = [mock_praw_submission]

            result = _praw_search_sync(
                query="test query",
                subreddit="python",
                sort="relevance",
                time_filter="all",
                limit=10,
                include_comments=True,
                client_id="test_id",
                client_secret="test_secret",
                user_agent="test_agent"
            )

            assert result["status"] == "success"
            assert result["provider"] == "praw"
            assert result["query"] == "test query"
            assert result["subreddit"] == "python"
            assert len(result["results"]) == 1

            post = result["results"][0]
            assert post["type"] == "post"
            assert post["title"] == "Test Post Title"
            assert post["subreddit"] == "r/testsubreddit"
            assert post["author"] == "u/testuser"
            assert post["score"] == 100

    def test_praw_search_all_subreddits(self, mock_praw_submission):
        """Test PRAW search across all subreddits when subreddit is None."""
        with patch('praw.Reddit') as mock_reddit_class:
            mock_reddit = MagicMock()
            mock_reddit_class.return_value = mock_reddit
            mock_subreddit = MagicMock()
            mock_reddit.subreddit.return_value = mock_subreddit
            mock_subreddit.search.return_value = [mock_praw_submission]

            result = _praw_search_sync(
                query="test",
                subreddit=None,
                sort="relevance",
                time_filter="all",
                limit=10,
                include_comments=False,
                client_id="test_id",
                client_secret="test_secret",
                user_agent="test_agent"
            )

            assert result["status"] == "success"
            assert result["subreddit"] == "all"
            mock_reddit.subreddit.assert_called_with("all")

    def test_praw_search_truncates_selftext(self, mock_praw_submission):
        """Test that selftext is truncated to 1000 chars."""
        mock_praw_submission.selftext = "x" * 2000  # Over 1000 chars

        with patch('praw.Reddit') as mock_reddit_class:
            mock_reddit = MagicMock()
            mock_reddit_class.return_value = mock_reddit
            mock_subreddit = MagicMock()
            mock_reddit.subreddit.return_value = mock_subreddit
            mock_subreddit.search.return_value = [mock_praw_submission]

            result = _praw_search_sync(
                query="test",
                subreddit=None,
                sort="relevance",
                time_filter="all",
                limit=10,
                include_comments=False,
                client_id="test_id",
                client_secret="test_secret",
                user_agent="test_agent"
            )

            assert len(result["results"][0]["selftext"]) == 1000

    def test_praw_search_handles_deleted_author(self, mock_praw_submission):
        """Test that deleted author is handled gracefully."""
        mock_praw_submission.author = None

        with patch('praw.Reddit') as mock_reddit_class:
            mock_reddit = MagicMock()
            mock_reddit_class.return_value = mock_reddit
            mock_subreddit = MagicMock()
            mock_reddit.subreddit.return_value = mock_subreddit
            mock_subreddit.search.return_value = [mock_praw_submission]

            result = _praw_search_sync(
                query="test",
                subreddit=None,
                sort="relevance",
                time_filter="all",
                limit=10,
                include_comments=False,
                client_id="test_id",
                client_secret="test_secret",
                user_agent="test_agent"
            )

            assert result["results"][0]["author"] == "[deleted]"

    def test_praw_search_forbidden_subreddit(self):
        """Test handling of private/forbidden subreddit."""
        from prawcore.exceptions import Forbidden

        with patch('praw.Reddit') as mock_reddit_class:
            mock_reddit = MagicMock()
            mock_reddit_class.return_value = mock_reddit
            mock_subreddit = MagicMock()
            mock_reddit.subreddit.return_value = mock_subreddit
            mock_subreddit.search.side_effect = Forbidden(MagicMock())

            result = _praw_search_sync(
                query="test",
                subreddit="privatesubreddit",
                sort="relevance",
                time_filter="all",
                limit=10,
                include_comments=False,
                client_id="test_id",
                client_secret="test_secret",
                user_agent="test_agent"
            )

            assert result["status"] == "error"
            assert result["error_code"] == "FORBIDDEN"
            assert "private" in result["error_message"].lower() or "forbidden" in result["error_message"].lower()

    def test_praw_search_not_found_subreddit(self):
        """Test handling of non-existent subreddit."""
        from prawcore.exceptions import NotFound

        with patch('praw.Reddit') as mock_reddit_class:
            mock_reddit = MagicMock()
            mock_reddit_class.return_value = mock_reddit
            mock_subreddit = MagicMock()
            mock_reddit.subreddit.return_value = mock_subreddit
            mock_subreddit.search.side_effect = NotFound(MagicMock())

            result = _praw_search_sync(
                query="test",
                subreddit="nonexistent",
                sort="relevance",
                time_filter="all",
                limit=10,
                include_comments=False,
                client_id="test_id",
                client_secret="test_secret",
                user_agent="test_agent"
            )

            assert result["status"] == "error"
            assert result["error_code"] == "NOT_FOUND"

    def test_praw_search_rate_limited(self):
        """Test handling of rate limiting."""
        from prawcore.exceptions import TooManyRequests

        with patch('praw.Reddit') as mock_reddit_class:
            mock_reddit = MagicMock()
            mock_reddit_class.return_value = mock_reddit
            mock_subreddit = MagicMock()
            mock_reddit.subreddit.return_value = mock_subreddit
            mock_subreddit.search.side_effect = TooManyRequests(MagicMock())

            result = _praw_search_sync(
                query="test",
                subreddit=None,
                sort="relevance",
                time_filter="all",
                limit=10,
                include_comments=False,
                client_id="test_id",
                client_secret="test_secret",
                user_agent="test_agent"
            )

            assert result["status"] == "error"
            assert result["error_code"] == "RATE_LIMITED"


# =============================================================================
# Test JSON API Fallback
# =============================================================================

class TestJSONAPIFallback:
    """Test JSON API fallback provider."""

    @pytest.mark.asyncio
    async def test_json_api_success(self, mock_json_api_response):
        """Test successful JSON API search."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_json_api_response

        with patch('mcp_server.tools.reddit_search.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await _reddit_json_search(
                query="test query",
                subreddit="python",
                sort="relevance",
                time_filter="all",
                limit=10,
                user_agent="test_agent"
            )

            assert result["status"] == "success"
            assert result["provider"] == "json_api"
            assert result["query"] == "test query"
            assert result["subreddit"] == "python"
            assert len(result["results"]) == 2

            # Verify first post
            post = result["results"][0]
            assert post["title"] == "JSON API Post Title"
            assert post["subreddit"] == "r/python"
            assert post["author"] == "u/jsonuser"
            assert post["comments"] == []  # JSON API doesn't include comments

    @pytest.mark.asyncio
    async def test_json_api_all_subreddits(self, mock_json_api_response):
        """Test JSON API search across all subreddits."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_json_api_response

        with patch('mcp_server.tools.reddit_search.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await _reddit_json_search(
                query="test",
                subreddit=None,
                sort="relevance",
                time_filter="all",
                limit=10,
                user_agent="test_agent"
            )

            assert result["subreddit"] == "all"
            # Verify correct URL used
            call_args = mock_client.get.call_args
            assert "search.json" in call_args[0][0]
            assert "/r/" not in call_args[0][0]

    @pytest.mark.asyncio
    async def test_json_api_subreddit_specific(self, mock_json_api_response):
        """Test JSON API search in specific subreddit."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_json_api_response

        with patch('mcp_server.tools.reddit_search.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await _reddit_json_search(
                query="test",
                subreddit="python",
                sort="relevance",
                time_filter="all",
                limit=10,
                user_agent="test_agent"
            )

            # Verify correct URL used
            call_args = mock_client.get.call_args
            assert "/r/python/search.json" in call_args[0][0]
            # Verify restrict_sr is set
            assert call_args[1]["params"]["restrict_sr"] == "on"

    @pytest.mark.asyncio
    async def test_json_api_rate_limited_with_retry(self):
        """Test JSON API handles rate limiting with retry."""
        mock_rate_limited = Mock()
        mock_rate_limited.status_code = 429

        mock_success = Mock()
        mock_success.status_code = 200
        mock_success.json.return_value = {"data": {"children": []}}

        with patch('mcp_server.tools.reddit_search.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            # First call rate limited, second succeeds
            mock_client.get = AsyncMock(side_effect=[mock_rate_limited, mock_success])
            mock_client_class.return_value = mock_client

            with patch('asyncio.sleep', new_callable=AsyncMock):
                result = await _reddit_json_search(
                    query="test",
                    subreddit=None,
                    sort="relevance",
                    time_filter="all",
                    limit=10,
                    user_agent="test_agent"
                )

            assert result["status"] == "success"
            assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_json_api_rate_limited_exhausted(self):
        """Test JSON API returns error after exhausting retries."""
        mock_rate_limited = Mock()
        mock_rate_limited.status_code = 429

        with patch('mcp_server.tools.reddit_search.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = AsyncMock(return_value=mock_rate_limited)
            mock_client_class.return_value = mock_client

            with patch('asyncio.sleep', new_callable=AsyncMock):
                result = await _reddit_json_search(
                    query="test",
                    subreddit=None,
                    sort="relevance",
                    time_filter="all",
                    limit=10,
                    user_agent="test_agent"
                )

            assert result["status"] == "error"
            assert result["error_code"] == "RATE_LIMITED"
            assert mock_client.get.call_count == 3  # All retries exhausted

    @pytest.mark.asyncio
    async def test_json_api_forbidden(self):
        """Test JSON API handles 403 Forbidden."""
        mock_response = Mock()
        mock_response.status_code = 403

        with patch('mcp_server.tools.reddit_search.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await _reddit_json_search(
                query="test",
                subreddit="privatesubreddit",
                sort="relevance",
                time_filter="all",
                limit=10,
                user_agent="test_agent"
            )

            assert result["status"] == "error"
            assert result["error_code"] == "FORBIDDEN"

    @pytest.mark.asyncio
    async def test_json_api_not_found(self):
        """Test JSON API handles 404 Not Found."""
        mock_response = Mock()
        mock_response.status_code = 404

        with patch('mcp_server.tools.reddit_search.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await _reddit_json_search(
                query="test",
                subreddit="nonexistent",
                sort="relevance",
                time_filter="all",
                limit=10,
                user_agent="test_agent"
            )

            assert result["status"] == "error"
            assert result["error_code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_json_api_timeout(self):
        """Test JSON API handles timeout."""
        with patch('mcp_server.tools.reddit_search.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_client_class.return_value = mock_client

            result = await _reddit_json_search(
                query="test",
                subreddit=None,
                sort="relevance",
                time_filter="all",
                limit=10,
                user_agent="test_agent"
            )

            assert result["status"] == "error"
            assert result["error_code"] == "TIMEOUT"

    @pytest.mark.asyncio
    async def test_json_api_filters_deleted_posts(self):
        """Test JSON API filters out deleted posts."""
        response_with_deleted = {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "Normal Post",
                            "subreddit": "test",
                            "author": "normaluser",
                            "score": 100,
                            "permalink": "/r/test/comments/abc/normal",
                            "selftext": "Content",
                            "num_comments": 5,
                            "created_utc": 1704067200.0
                        }
                    },
                    {
                        "data": {
                            "title": "Deleted Post",
                            "subreddit": "test",
                            "author": "[deleted]",
                            "score": 50,
                            "permalink": "/r/test/comments/def/deleted",
                            "selftext": "[removed]",
                            "num_comments": 0,
                            "created_utc": 1704067200.0
                        }
                    }
                ]
            }
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = response_with_deleted

        with patch('mcp_server.tools.reddit_search.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await _reddit_json_search(
                query="test",
                subreddit=None,
                sort="relevance",
                time_filter="all",
                limit=10,
                user_agent="test_agent"
            )

            # Should only include the non-deleted post
            assert len(result["results"]) == 1
            assert result["results"][0]["author"] == "u/normaluser"


# =============================================================================
# Test Fallback Logic
# =============================================================================

class TestFallbackLogic:
    """Test fallback from PRAW to JSON API."""

    @pytest.mark.asyncio
    async def test_fallback_when_no_credentials(self, mock_json_api_response):
        """Test falls back to JSON API when no credentials."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_json_api_response

        with patch('mcp_server.tools.reddit_search.get_config', return_value={}):
            with patch('mcp_server.tools.reddit_search.httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client

                result = await reddit_search_tool_handler(query="test")

                assert result["status"] == "success"
                assert result["provider"] == "json_api"

    @pytest.mark.asyncio
    async def test_fallback_when_praw_fails(self, mock_json_api_response, mock_config_with_reddit):
        """Test falls back to JSON API when PRAW fails."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_json_api_response

        with patch('mcp_server.tools.reddit_search.get_config', return_value=mock_config_with_reddit):
            # Make PRAW fail
            with patch('mcp_server.tools.reddit_search._praw_search_sync', return_value={
                "status": "error",
                "provider": "praw",
                "query": "test",
                "error_message": "OAuth failed",
                "error_code": "API_ERROR"
            }):
                with patch('mcp_server.tools.reddit_search.httpx.AsyncClient') as mock_client_class:
                    mock_client = AsyncMock()
                    mock_client.__aenter__.return_value = mock_client
                    mock_client.__aexit__.return_value = None
                    mock_client.get = AsyncMock(return_value=mock_response)
                    mock_client_class.return_value = mock_client

                    result = await reddit_search_tool_handler(query="test")

                    assert result["status"] == "success"
                    assert result["provider"] == "json_api"

    @pytest.mark.asyncio
    async def test_praw_success_no_fallback(self, mock_config_with_reddit):
        """Test no fallback when PRAW succeeds."""
        with patch('mcp_server.tools.reddit_search.get_config', return_value=mock_config_with_reddit):
            with patch('mcp_server.tools.reddit_search._praw_search_sync', return_value={
                "status": "success",
                "provider": "praw",
                "query": "test",
                "subreddit": "all",
                "results": [{"type": "post", "title": "Test"}]
            }):
                with patch('mcp_server.tools.reddit_search._reddit_json_search', new_callable=AsyncMock) as mock_json:
                    result = await reddit_search_tool_handler(query="test")

                    assert result["status"] == "success"
                    assert result["provider"] == "praw"
                    # JSON API should not have been called
                    mock_json.assert_not_called()


# =============================================================================
# Test Include Comments
# =============================================================================

class TestIncludeComments:
    """Test include_comments functionality."""

    def test_include_comments_true_fetches_comments(self, mock_praw_submission):
        """Test that include_comments=True fetches comments."""
        with patch('praw.Reddit') as mock_reddit_class:
            mock_reddit = MagicMock()
            mock_reddit_class.return_value = mock_reddit
            mock_subreddit = MagicMock()
            mock_reddit.subreddit.return_value = mock_subreddit
            mock_subreddit.search.return_value = [mock_praw_submission]

            result = _praw_search_sync(
                query="test",
                subreddit=None,
                sort="relevance",
                time_filter="all",
                limit=10,
                include_comments=True,
                client_id="test_id",
                client_secret="test_secret",
                user_agent="test_agent"
            )

            # Verify replace_more was called
            mock_praw_submission.comments.replace_more.assert_called_once_with(limit=0)

    def test_include_comments_false_skips_comments(self, mock_praw_submission):
        """Test that include_comments=False skips comments."""
        with patch('praw.Reddit') as mock_reddit_class:
            mock_reddit = MagicMock()
            mock_reddit_class.return_value = mock_reddit
            mock_subreddit = MagicMock()
            mock_reddit.subreddit.return_value = mock_subreddit
            mock_subreddit.search.return_value = [mock_praw_submission]

            result = _praw_search_sync(
                query="test",
                subreddit=None,
                sort="relevance",
                time_filter="all",
                limit=10,
                include_comments=False,
                client_id="test_id",
                client_secret="test_secret",
                user_agent="test_agent"
            )

            # Verify replace_more was NOT called
            mock_praw_submission.comments.replace_more.assert_not_called()
            # Comments should be empty
            assert result["results"][0]["comments"] == []


# =============================================================================
# Test Sort and Time Filter
# =============================================================================

class TestSortAndTimeFilter:
    """Test sort and time_filter parameters."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("sort", ["relevance", "hot", "top", "new"])
    async def test_all_sort_options(self, sort, mock_json_api_response):
        """Test all sort options work."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_json_api_response

        with patch('mcp_server.tools.reddit_search.get_config', return_value={}):
            with patch('mcp_server.tools.reddit_search.httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client

                result = await reddit_search_tool_handler(query="test", sort=sort)

                assert result["status"] == "success"
                # Verify sort was passed to API
                call_args = mock_client.get.call_args
                assert call_args[1]["params"]["sort"] == sort

    @pytest.mark.asyncio
    @pytest.mark.parametrize("time_filter", ["hour", "day", "week", "month", "year", "all"])
    async def test_all_time_filter_options(self, time_filter, mock_json_api_response):
        """Test all time_filter options work."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_json_api_response

        with patch('mcp_server.tools.reddit_search.get_config', return_value={}):
            with patch('mcp_server.tools.reddit_search.httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client

                result = await reddit_search_tool_handler(query="test", time_filter=time_filter)

                assert result["status"] == "success"
                # Verify time filter was passed to API (as 't' parameter)
                call_args = mock_client.get.call_args
                assert call_args[1]["params"]["t"] == time_filter
