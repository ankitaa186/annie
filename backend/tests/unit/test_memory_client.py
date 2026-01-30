"""
Unit tests for MemoryClient
"""

import json
import pytest
from unittest.mock import AsyncMock, Mock, patch
import httpx

from api.memory_client import (
    MemoryClient,
    MemoryClientError,
    MemoryNetworkError,
    MemoryAPIError
)


@pytest.fixture
def memory_client():
    """Create MemoryClient instance for testing."""
    return MemoryClient(memories_url="http://test-memories:8080", timeout=5.0)


@pytest.fixture
def sample_memory():
    """Sample memory object for testing."""
    return {
        "memory_id": "mem_test123",
        "timestamp": "2025-11-11T10:00:00Z",
        "conversation_summary": "User asked for stock advice",
        "decisions": [
            {
                "decision": "Buy 10 shares of AAPL",
                "options_considered": ["Buy AAPL", "Buy MSFT", "Hold cash"],
                "reasoning": "Strong fundamentals",
                "outcome": None
            }
        ],
        "preferences": {
            "risk_tolerance": "moderate",
            "priorities": ["long-term growth"],
            "constraints": ["max 20% tech exposure"]
        },
        "topics": ["stock_trading", "AAPL"],
        "sentiment": "positive"
    }


class TestMemoryClientInit:
    """Test MemoryClient initialization."""

    def test_init_with_default_config(self):
        """Test initialization with default configuration from environment."""
        client = MemoryClient()
        # Uses AGENTIC_MEMORIES_URL from test environment (conftest.py)
        assert client.memories_url == "http://localhost:8080"
        assert client.timeout == 240.0  # 4 minute default timeout
        assert client.client is not None

    def test_init_with_custom_config(self):
        """Test initialization with custom configuration."""
        client = MemoryClient(memories_url="http://custom:9000", timeout=10.0)
        assert client.memories_url == "http://custom:9000"
        assert client.timeout == 10.0

    def test_init_with_config_from_env(self):
        """Test initialization loads from config."""
        with patch('api.memory_client.get_config') as mock_config:
            mock_config.return_value = {"AGENTIC_MEMORIES_URL": "http://env:8080"}
            client = MemoryClient()
            assert client.memories_url == "http://env:8080"


class TestMemoryClientContextManager:
    """Test async context manager."""

    @pytest.mark.asyncio
    async def test_context_manager(self, memory_client):
        """Test async context manager works correctly."""
        async with memory_client as client:
            assert client is memory_client
            assert client.client is not None

        # Client should be closed after context exit
        # httpx client's is_closed property would be True
        # But we can't easily test that without actual connection


class TestStoreMemory:
    """Test store_memory method."""

    @pytest.mark.asyncio
    async def test_store_memory_success(self, memory_client, sample_memory):
        """Test successful memory storage."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "memory_id": "mem_test123",
            "stored_at": "2025-11-11T10:00:00Z"
        }

        with patch.object(memory_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await memory_client.store_memory("user123", sample_memory)

            # Verify result
            assert result["status"] == "success"
            assert result["memory_id"] == "mem_test123"
            assert result["stored_at"] == "2025-11-11T10:00:00Z"

            # Verify POST was called correctly
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert call_args[0][0] == "http://test-memories:8080/v1/store"
            assert call_args[1]["json"]["user_id"] == "user123"
            assert call_args[1]["json"]["history"] == sample_memory

    @pytest.mark.asyncio
    async def test_store_memory_api_error(self, memory_client, sample_memory):
        """Test memory storage with API error."""
        # Mock error response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {
            "message": "Internal server error"
        }
        mock_response.text = "Internal server error"

        with patch.object(memory_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            with pytest.raises(MemoryAPIError) as exc_info:
                await memory_client.store_memory("user123", sample_memory)

            assert exc_info.value.status_code == 500
            assert "Internal server error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_store_memory_network_error(self, memory_client, sample_memory):
        """Test memory storage with network error."""
        with patch.object(memory_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.ConnectError("Connection refused")

            with pytest.raises(MemoryNetworkError) as exc_info:
                await memory_client.store_memory("user123", sample_memory)

            assert "Failed to connect" in str(exc_info.value)
            assert exc_info.value.original_error is not None

    @pytest.mark.asyncio
    async def test_store_memory_timeout(self, memory_client, sample_memory):
        """Test memory storage with timeout."""
        with patch.object(memory_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Request timed out")

            with pytest.raises(MemoryNetworkError) as exc_info:
                await memory_client.store_memory("user123", sample_memory)

            assert "timed out" in str(exc_info.value)
            assert exc_info.value.original_error is not None

    @pytest.mark.asyncio
    async def test_store_memory_http_error(self, memory_client, sample_memory):
        """Test memory storage with generic HTTP error."""
        with patch.object(memory_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.HTTPError("Generic HTTP error")

            with pytest.raises(MemoryNetworkError) as exc_info:
                await memory_client.store_memory("user123", sample_memory)

            assert "HTTP error" in str(exc_info.value)


class TestHealthCheck:
    """Test health_check method."""

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, memory_client):
        """Test health check when service is healthy."""
        mock_response = Mock()
        mock_response.status_code = 200

        with patch.object(memory_client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            result = await memory_client.health_check()

            assert result is True
            mock_get.assert_called_once_with("http://test-memories:8080/health")

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, memory_client):
        """Test health check when service is unhealthy."""
        mock_response = Mock()
        mock_response.status_code = 503

        with patch.object(memory_client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            result = await memory_client.health_check()

            assert result is False

    @pytest.mark.asyncio
    async def test_health_check_network_error(self, memory_client):
        """Test health check with network error."""
        with patch.object(memory_client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.ConnectError("Connection refused")

            result = await memory_client.health_check()

            assert result is False


class TestRetrieveMemories:
    """Test retrieve_memories method."""

    @pytest.mark.asyncio
    async def test_retrieve_memories_success(self, memory_client):
        """Test successful memory retrieval."""
        # Mock successful response with memories
        # Note: agentic-memories API returns "results" field
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "memory_id": "mem_1",
                    "conversation_summary": "User asked for stock advice",
                    "decisions": [{"decision": "Buy AAPL"}],
                    "preferences": {"risk_tolerance": "moderate"},
                    "topics": ["stocks"],
                    "relevance_score": 0.95,
                    "timestamp": "2025-11-10T10:00:00Z"
                },
                {
                    "memory_id": "mem_2",
                    "conversation_summary": "Discussed investment strategy",
                    "decisions": [],
                    "preferences": {"priorities": ["long-term growth"]},
                    "topics": ["investing"],
                    "relevance_score": 0.85,
                    "timestamp": "2025-11-09T15:30:00Z"
                }
            ],
            "total_count": 2
        }

        with patch.object(memory_client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            result = await memory_client.retrieve_memories("user123", "stock investment")

            # Verify result
            assert isinstance(result, list)
            assert len(result) == 2
            assert result[0]["memory_id"] == "mem_1"
            assert result[0]["relevance_score"] == 0.95
            assert result[1]["memory_id"] == "mem_2"

            # Verify GET was called correctly with query parameters
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert call_args[0][0] == "http://test-memories:8080/v1/retrieve"
            assert call_args[1]["params"]["user_id"] == "user123"
            assert call_args[1]["params"]["query"] == "stock investment"
            assert call_args[1]["params"]["limit"] == 5
            assert call_args[1]["timeout"] == 0.3  # 300ms timeout

    @pytest.mark.asyncio
    async def test_retrieve_memories_with_persona(self, memory_client):
        """Test memory retrieval with persona filter."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"memories": [], "total_count": 0}

        with patch.object(memory_client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            result = await memory_client.retrieve_memories(
                "user123",
                "stock investment",
                limit=10,
                persona="stock_trader"
            )

            # Verify persona parameter was passed
            call_args = mock_get.call_args
            assert call_args[1]["params"]["persona"] == "stock_trader"
            assert call_args[1]["params"]["limit"] == 10

    @pytest.mark.asyncio
    async def test_retrieve_memories_empty_result(self, memory_client):
        """Test memory retrieval with no results."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"memories": [], "total_count": 0}

        with patch.object(memory_client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            result = await memory_client.retrieve_memories("user123", "nonexistent query")

            assert result == []

    @pytest.mark.asyncio
    async def test_retrieve_memories_timeout_graceful_degradation(self, memory_client):
        """Test memory retrieval timeout returns empty list (graceful degradation)."""
        with patch.object(memory_client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.TimeoutException("Request timed out")

            # Should return empty list instead of raising exception
            result = await memory_client.retrieve_memories("user123", "query")

            assert result == []

    @pytest.mark.asyncio
    async def test_retrieve_memories_network_error_graceful_degradation(self, memory_client):
        """Test memory retrieval network error returns empty list (graceful degradation)."""
        with patch.object(memory_client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.ConnectError("Connection refused")

            # Should return empty list instead of raising exception
            result = await memory_client.retrieve_memories("user123", "query")

            assert result == []

    @pytest.mark.asyncio
    async def test_retrieve_memories_http_error_graceful_degradation(self, memory_client):
        """Test memory retrieval HTTP error returns empty list (graceful degradation)."""
        with patch.object(memory_client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.HTTPError("Generic HTTP error")

            # Should return empty list instead of raising exception
            result = await memory_client.retrieve_memories("user123", "query")

            assert result == []

    @pytest.mark.asyncio
    async def test_retrieve_memories_api_error_graceful_degradation(self, memory_client):
        """Test memory retrieval API error returns empty list (graceful degradation)."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"message": "Internal server error"}
        mock_response.text = "Internal server error"

        with patch.object(memory_client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            # API errors should still raise exception (not gracefully degraded)
            with pytest.raises(MemoryAPIError) as exc_info:
                await memory_client.retrieve_memories("user123", "query")

            assert exc_info.value.status_code == 500


class TestExceptionHierarchy:
    """Test custom exception hierarchy."""

    def test_memory_client_error_base(self):
        """Test MemoryClientError is base exception."""
        error = MemoryClientError("Test error")
        assert isinstance(error, Exception)
        assert str(error) == "Test error"

    def test_memory_network_error(self):
        """Test MemoryNetworkError exception."""
        original = Exception("Original error")
        error = MemoryNetworkError("Network error", original_error=original)
        assert isinstance(error, MemoryClientError)
        assert error.message == "Network error"
        assert error.original_error is original

    def test_memory_api_error(self):
        """Test MemoryAPIError exception."""
        error = MemoryAPIError("API error", status_code=500, response_data={"error": "test"})
        assert isinstance(error, MemoryClientError)
        assert error.message == "API error"
        assert error.status_code == 500
        assert error.response_data == {"error": "test"}
        assert "500" in str(error)


class TestStreamMessage:
    """Test stream_message method for orchestrator integration."""

    @pytest.mark.asyncio
    async def test_stream_message_success(self, memory_client):
        """Test successful message streaming to orchestrator."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "injections": [
                {
                    "memory_id": "mem_abc",
                    "content": "User prefers tech stocks",
                    "source": "LONG_TERM",
                    "channel": "INLINE",
                    "score": 0.85,
                    "metadata": {}
                }
            ]
        }

        with patch.object(memory_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await memory_client.stream_message(
                conversation_id="conv_123",
                role="user",
                content="What stocks should I buy?",
                user_id="user_456"
            )

            # Verify result structure
            assert "injections" in result
            assert len(result["injections"]) == 1
            assert result["injections"][0]["memory_id"] == "mem_abc"
            assert result["injections"][0]["score"] == 0.85

            # Verify POST was called correctly
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert call_args[0][0] == "http://test-memories:8080/v1/orchestrator/message"
            payload = call_args[1]["json"]
            assert payload["conversation_id"] == "conv_123"
            assert payload["role"] == "user"
            assert payload["content"] == "What stocks should I buy?"
            assert payload["metadata"]["user_id"] == "user_456"
            assert payload["flush"] is False

    @pytest.mark.asyncio
    async def test_stream_message_with_flush(self, memory_client):
        """Test message streaming with flush=True."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"injections": []}

        with patch.object(memory_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            await memory_client.stream_message(
                conversation_id="conv_123",
                role="assistant",
                content="Here is my response",
                user_id="user_456",
                flush=True
            )

            # Verify flush parameter was passed
            call_args = mock_post.call_args
            payload = call_args[1]["json"]
            assert payload["flush"] is True
            assert payload["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_stream_message_with_message_id(self, memory_client):
        """Test message streaming with optional message_id."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"injections": []}

        with patch.object(memory_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            await memory_client.stream_message(
                conversation_id="conv_123",
                role="user",
                content="Test message",
                user_id="user_456",
                message_id="msg_789"
            )

            # Verify message_id was included
            call_args = mock_post.call_args
            payload = call_args[1]["json"]
            assert payload["message_id"] == "msg_789"

    @pytest.mark.asyncio
    async def test_stream_message_empty_injections(self, memory_client):
        """Test message streaming with no injections returned."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"injections": []}

        with patch.object(memory_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await memory_client.stream_message(
                conversation_id="conv_new",
                role="user",
                content="Hello",
                user_id="new_user"
            )

            assert result["injections"] == []

    @pytest.mark.asyncio
    async def test_stream_message_api_error(self, memory_client):
        """Test message streaming with API error."""
        mock_response = Mock()
        mock_response.status_code = 422
        mock_response.json.return_value = {"detail": "Invalid role"}
        mock_response.text = "Invalid role"

        with patch.object(memory_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            with pytest.raises(MemoryAPIError) as exc_info:
                await memory_client.stream_message(
                    conversation_id="conv_123",
                    role="invalid_role",
                    content="Test",
                    user_id="user_456"
                )

            assert exc_info.value.status_code == 422
            assert "Invalid role" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_stream_message_network_error(self, memory_client):
        """Test message streaming with network error."""
        with patch.object(memory_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.ConnectError("Connection refused")

            with pytest.raises(MemoryNetworkError) as exc_info:
                await memory_client.stream_message(
                    conversation_id="conv_123",
                    role="user",
                    content="Test",
                    user_id="user_456"
                )

            assert "Failed to connect to orchestrator" in str(exc_info.value)
            assert exc_info.value.original_error is not None

    @pytest.mark.asyncio
    async def test_stream_message_timeout(self, memory_client):
        """Test message streaming with timeout."""
        with patch.object(memory_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Request timed out")

            with pytest.raises(MemoryNetworkError) as exc_info:
                await memory_client.stream_message(
                    conversation_id="conv_123",
                    role="user",
                    content="Test",
                    user_id="user_456"
                )

            assert "timed out" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_stream_message_http_error(self, memory_client):
        """Test message streaming with generic HTTP error."""
        with patch.object(memory_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.HTTPError("Generic HTTP error")

            with pytest.raises(MemoryNetworkError) as exc_info:
                await memory_client.stream_message(
                    conversation_id="conv_123",
                    role="user",
                    content="Test",
                    user_id="user_456"
                )

            assert "HTTP error" in str(exc_info.value)


class TestStoreDirect:
    """Test store_direct method for direct memory storage."""

    @pytest.mark.asyncio
    async def test_store_direct_success(self, memory_client):
        """Test successful direct memory storage."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "mem_direct_123",
            "status": "created"
        }

        with patch.object(memory_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await memory_client.store_direct(
                user_id="user_456",
                content="User decided to hold NVDA despite the dip",
                layer="long-term",
                memory_type="explicit",
                tags=["conversation_summary", "echoes"],
                metadata={"conversation_id": "conv_789", "source": "session_flush_summary"}
            )

            assert result["id"] == "mem_direct_123"

            # Verify POST was called correctly
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert call_args[0][0] == "http://test-memories:8080/v1/memories/direct"
            payload = call_args[1]["json"]
            assert payload["user_id"] == "user_456"
            assert payload["content"] == "User decided to hold NVDA despite the dip"
            assert payload["layer"] == "long-term"
            assert payload["type"] == "explicit"
            assert payload["tags"] == ["conversation_summary", "echoes"]
            assert payload["metadata"]["conversation_id"] == "conv_789"

    @pytest.mark.asyncio
    async def test_store_direct_success_200(self, memory_client):
        """Test store_direct accepts both 200 and 201 status codes."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "mem_ok"}

        with patch.object(memory_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await memory_client.store_direct(
                user_id="user_1",
                content="Some memory content"
            )

            assert result["id"] == "mem_ok"

    @pytest.mark.asyncio
    async def test_store_direct_minimal_params(self, memory_client):
        """Test store_direct with only required parameters."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "mem_min"}

        with patch.object(memory_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await memory_client.store_direct(
                user_id="user_1",
                content="Minimal memory"
            )

            assert result["id"] == "mem_min"

            # Verify defaults
            payload = mock_post.call_args[1]["json"]
            assert payload["layer"] == "long-term"
            assert payload["type"] == "explicit"
            assert "tags" not in payload
            assert "metadata" not in payload

    @pytest.mark.asyncio
    async def test_store_direct_api_error(self, memory_client):
        """Test store_direct with API error."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"detail": "Content too long"}
        mock_response.text = "Content too long"

        with patch.object(memory_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            with pytest.raises(MemoryAPIError) as exc_info:
                await memory_client.store_direct(
                    user_id="user_1",
                    content="x" * 10000
                )

            assert exc_info.value.status_code == 400
            assert "Content too long" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_store_direct_network_error(self, memory_client):
        """Test store_direct with network error."""
        with patch.object(memory_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.ConnectError("Connection refused")

            with pytest.raises(MemoryNetworkError) as exc_info:
                await memory_client.store_direct(
                    user_id="user_1",
                    content="test"
                )

            assert "Failed to connect" in str(exc_info.value)
            assert exc_info.value.original_error is not None

    @pytest.mark.asyncio
    async def test_store_direct_timeout(self, memory_client):
        """Test store_direct with timeout."""
        with patch.object(memory_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Request timed out")

            with pytest.raises(MemoryNetworkError) as exc_info:
                await memory_client.store_direct(
                    user_id="user_1",
                    content="test"
                )

            assert "timed out" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_store_direct_http_error(self, memory_client):
        """Test store_direct with generic HTTP error."""
        with patch.object(memory_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.HTTPError("Generic HTTP error")

            with pytest.raises(MemoryNetworkError) as exc_info:
                await memory_client.store_direct(
                    user_id="user_1",
                    content="test"
                )

            assert "HTTP error" in str(exc_info.value)
