"""
Integration tests for end-to-end streaming flow.

Tests complete flow from POST /api/chat to GET /api/stream with
real-like interactions between components.
"""

import json
import time
from unittest.mock import AsyncMock, Mock, patch
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routes.stream import active_streams


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_active_streams():
    """Reset active streams before each test."""
    active_streams.clear()
    yield
    active_streams.clear()


class TestEndToEndStreaming:
    """End-to-end integration tests for chat and streaming."""

    def test_complete_chat_to_stream_flow(self, client):
        """Test complete flow: POST /api/chat -> GET /api/stream."""
        # Step 1: Create chat conversation
        chat_request = {
            "user_id": "test_user_123",
            "platform": "telegram",
            "message": "Hello, how are you?",
            "context": {}
        }

        response = client.post("/api/chat", json=chat_request)
        assert response.status_code == 200

        chat_response = response.json()
        assert "conversation_id" in chat_response
        assert chat_response["status"] == "streaming"
        assert "stream_url" in chat_response

        conversation_id = chat_response["conversation_id"]
        stream_url = chat_response["stream_url"]

        # Step 2: Connect to streaming endpoint
        with patch('api.routes.stream.LLMClient') as MockLLMClient, \
             patch('api.routes.stream.MCPClient') as MockMCPClient:

            # Mock LLM client
            mock_llm_instance = Mock()
            MockLLMClient.return_value.__aenter__.return_value = mock_llm_instance
            mock_llm_instance.convert_mcp_tools_to_functions = Mock(return_value=[])

            # Mock MCP client
            mock_mcp_instance = AsyncMock()
            MockMCPClient.return_value.__aenter__.return_value = mock_mcp_instance
            mock_mcp_instance.list_tools = AsyncMock(return_value=[])

            # Mock non-streaming call (returns no tool calls)
            mock_llm_instance.chat_completion = AsyncMock(return_value={
                "choices": [{"message": {"role": "assistant", "content": "test"}}]
            })

            # Mock streaming response
            async def mock_stream(messages, tools=None):
                yield {"type": "token", "content": "I'm"}
                yield {"type": "token", "content": " doing"}
                yield {"type": "token", "content": " well!"}
                yield {"type": "done", "tokens_used": {"prompt": 15, "completion": 3}}

            mock_llm_instance.chat_completion_stream = mock_stream

            # Make streaming request
            with client.stream("GET", stream_url) as stream_response:
                assert stream_response.status_code == 200
                assert stream_response.headers["content-type"] == "text/event-stream; charset=utf-8"

                # Collect all tokens
                tokens = []
                completion_event = None

                for line in stream_response.iter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        event = json.loads(data_str)

                        if event["type"] == "token":
                            tokens.append(event["content"])
                        elif event["type"] == "done":
                            completion_event = event

                # Verify complete response
                assert tokens == ["I'm", " doing", " well!"]
                assert completion_event is not None
                assert completion_event["tokens_used"]["prompt"] == 15
                assert completion_event["tokens_used"]["completion"] == 3

    def test_concurrent_streams(self, client):
        """Test handling multiple concurrent streaming connections."""
        # Create multiple chat conversations
        conversation_ids = []

        for i in range(5):
            chat_request = {
                "user_id": f"test_user_{i}",
                "platform": "telegram",
                "message": f"Message {i}",
                "context": {}
            }

            response = client.post("/api/chat", json=chat_request)
            assert response.status_code == 200

            conversation_id = response.json()["conversation_id"]
            conversation_ids.append(conversation_id)

        # Mock LLM client for concurrent streams
        with patch('api.routes.stream.LLMClient') as MockLLMClient, \
             patch('api.routes.stream.MCPClient') as MockMCPClient:

            # Mock LLM client
            mock_llm_instance = Mock()
            MockLLMClient.return_value.__aenter__.return_value = mock_llm_instance
            mock_llm_instance.convert_mcp_tools_to_functions = Mock(return_value=[])

            # Mock MCP client
            mock_mcp_instance = AsyncMock()
            MockMCPClient.return_value.__aenter__.return_value = mock_mcp_instance
            mock_mcp_instance.list_tools = AsyncMock(return_value=[])

            # Mock non-streaming call (returns no tool calls)
            mock_llm_instance.chat_completion = AsyncMock(return_value={
                "choices": [{"message": {"role": "assistant", "content": "test"}}]
            })

            async def mock_stream(messages, tools=None):
                yield {"type": "token", "content": "Response"}
                yield {"type": "done", "tokens_used": {"prompt": 10, "completion": 1}}

            mock_llm_instance.chat_completion_stream = mock_stream

            # Test that all streams can be established concurrently
            # (Note: TestClient doesn't support true async, so we test sequentially)
            for conversation_id in conversation_ids:
                with client.stream("GET", f"/api/stream/{conversation_id}") as response:
                    assert response.status_code == 200

                    # Read at least one event to verify stream works
                    found_event = False
                    for line in response.iter_lines():
                        if line.startswith("data: "):
                            found_event = True
                            break

                    assert found_event

    def test_first_token_latency(self, client):
        """Test that first token arrives within acceptable latency."""
        # Create chat conversation
        chat_request = {
            "user_id": "test_user_latency",
            "platform": "telegram",
            "message": "Test latency",
            "context": {}
        }

        response = client.post("/api/chat", json=chat_request)
        assert response.status_code == 200

        conversation_id = response.json()["conversation_id"]

        with patch('api.routes.stream.LLMClient') as MockLLMClient, \
             patch('api.routes.stream.MCPClient') as MockMCPClient:

            # Mock LLM client
            mock_llm_instance = Mock()
            MockLLMClient.return_value.__aenter__.return_value = mock_llm_instance
            mock_llm_instance.convert_mcp_tools_to_functions = Mock(return_value=[])

            # Mock MCP client
            mock_mcp_instance = AsyncMock()
            MockMCPClient.return_value.__aenter__.return_value = mock_mcp_instance
            mock_mcp_instance.list_tools = AsyncMock(return_value=[])

            # Mock non-streaming call (returns no tool calls)
            mock_llm_instance.chat_completion = AsyncMock(return_value={
                "choices": [{"message": {"role": "assistant", "content": "test"}}]
            })

            # Mock streaming response with immediate first token
            async def mock_stream(messages, tools=None):
                # Simulate fast first token
                yield {"type": "token", "content": "Fast"}
                yield {"type": "done", "tokens_used": {"prompt": 5, "completion": 1}}

            mock_llm_instance.chat_completion_stream = mock_stream

            # Measure time to first token
            start_time = time.time()
            first_token_time = None

            with client.stream("GET", f"/api/stream/{conversation_id}") as stream_response:
                assert stream_response.status_code == 200

                for line in stream_response.iter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        event = json.loads(data_str)

                        if event["type"] == "token" and first_token_time is None:
                            first_token_time = time.time()
                            break

            # Verify first token arrived quickly (within 500ms would be ideal,
            # but in tests with mocks it should be nearly instant)
            assert first_token_time is not None
            latency_ms = (first_token_time - start_time) * 1000
            assert latency_ms < 1000  # Generous limit for test environment

    def test_error_recovery_in_stream(self, client):
        """Test error handling and recovery in streaming flow."""
        # Create chat conversation
        chat_request = {
            "user_id": "test_user_error",
            "platform": "telegram",
            "message": "Trigger error",
            "context": {}
        }

        response = client.post("/api/chat", json=chat_request)
        assert response.status_code == 200

        conversation_id = response.json()["conversation_id"]

        with patch('api.routes.stream.LLMClient') as MockLLMClient, \
             patch('api.routes.stream.MCPClient') as MockMCPClient:

            # Mock LLM client
            mock_llm_instance = Mock()
            MockLLMClient.return_value.__aenter__.return_value = mock_llm_instance
            mock_llm_instance.convert_mcp_tools_to_functions = Mock(return_value=[])

            # Mock MCP client
            mock_mcp_instance = AsyncMock()
            MockMCPClient.return_value.__aenter__.return_value = mock_mcp_instance
            mock_mcp_instance.list_tools = AsyncMock(return_value=[])

            # Mock non-streaming call (returns no tool calls)
            mock_llm_instance.chat_completion = AsyncMock(return_value={
                "choices": [{"message": {"role": "assistant", "content": "test"}}]
            })

            # Mock streaming response with error
            async def mock_stream(messages, tools=None):
                yield {"type": "token", "content": "Start"}
                # Simulate LLM error mid-stream
                yield {
                    "type": "error",
                    "message": "Rate limit exceeded",
                    "code": "RATE_LIMIT_ERROR"
                }

            mock_llm_instance.chat_completion_stream = mock_stream

            with client.stream("GET", f"/api/stream/{conversation_id}") as stream_response:
                assert stream_response.status_code == 200

                events = []
                for line in stream_response.iter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        events.append(json.loads(data_str))

                # Verify we got partial response and error
                assert len(events) >= 2
                assert events[0]["type"] == "token"
                assert events[1]["type"] == "error"
                assert "rate limit" in events[1]["message"].lower()

    def test_invalid_conversation_id(self, client):
        """Test handling of invalid conversation ID."""
        # Try to stream from non-existent conversation
        invalid_id = "conv_nonexistent"

        with patch('api.routes.stream.LLMClient') as MockLLMClient:
            mock_client_instance = Mock()
            MockLLMClient.return_value.__aenter__.return_value = mock_client_instance

            # Mock empty stream (simulating no conversation found)
            async def mock_stream(messages):
                # For now, we'll just yield a normal response
                # TODO: In Story 2.5, implement proper conversation validation
                yield {"type": "token", "content": "Response"}
                yield {"type": "done", "tokens_used": {"prompt": 5, "completion": 1}}

            mock_client_instance.chat_completion_stream = mock_stream

            # Should still return 200 (for now, until Redis validation in Story 2.5)
            with client.stream("GET", f"/api/stream/{invalid_id}") as response:
                assert response.status_code == 200


class TestChatEndpoint:
    """Integration tests for chat endpoint."""

    def test_chat_endpoint_validation(self, client):
        """Test input validation on chat endpoint."""
        # Test missing required fields
        invalid_request = {
            "user_id": "test_user"
            # Missing platform and message
        }

        response = client.post("/api/chat", json=invalid_request)
        assert response.status_code == 422  # Validation error

    def test_chat_endpoint_empty_message(self, client):
        """Test chat endpoint rejects empty message."""
        invalid_request = {
            "user_id": "test_user",
            "platform": "telegram",
            "message": "",  # Empty message
            "context": {}
        }

        response = client.post("/api/chat", json=invalid_request)
        assert response.status_code == 422  # Validation error

    def test_chat_endpoint_generates_unique_ids(self, client):
        """Test that each chat request generates a unique conversation ID."""
        chat_request = {
            "user_id": "test_user",
            "platform": "telegram",
            "message": "Test message",
            "context": {}
        }

        # Make multiple requests
        conversation_ids = set()

        for _ in range(5):
            response = client.post("/api/chat", json=chat_request)
            assert response.status_code == 200

            conversation_id = response.json()["conversation_id"]
            conversation_ids.add(conversation_id)

        # All IDs should be unique
        assert len(conversation_ids) == 5
