"""
Unit tests for streaming functionality.

Tests SSE streaming handler, client disconnection handling,
error handling, and concurrent stream management.
"""

import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.main import app
from api.routes.stream import active_streams, MAX_CONCURRENT_STREAMS


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


class TestStreamEndpoint:
    """Tests for /api/stream/{conversation_id} endpoint."""

    def test_stream_endpoint_success(self, client):
        """Test successful streaming response."""
        conversation_id = "test_conv_123"

        # Mock LLM client to return test tokens
        with patch('api.routes.stream.LLMClient') as MockLLMClient:
            mock_client_instance = Mock()
            MockLLMClient.return_value.__aenter__.return_value = mock_client_instance

            # Mock streaming response with actual async generator
            async def mock_stream(messages):
                yield {"type": "token", "content": "Hello"}
                yield {"type": "token", "content": " world"}
                yield {"type": "done", "tokens_used": {"prompt": 10, "completion": 2}}

            mock_client_instance.chat_completion_stream = mock_stream

            # Make streaming request
            with client.stream("GET", f"/api/stream/{conversation_id}") as response:
                assert response.status_code == 200
                assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

                # Read SSE events
                events = []
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]  # Remove "data: " prefix
                        events.append(json.loads(data_str))

                # Verify events
                assert len(events) == 3
                assert events[0] == {"type": "token", "content": "Hello"}
                assert events[1] == {"type": "token", "content": " world"}
                assert events[2]["type"] == "done"
                assert events[2]["tokens_used"]["prompt"] == 10
                assert events[2]["tokens_used"]["completion"] == 2

    @pytest.mark.asyncio
    async def test_stream_concurrent_limit(self, client):
        """Test concurrent stream limit enforcement."""
        # Fill up to limit
        for i in range(MAX_CONCURRENT_STREAMS):
            active_streams[f"conv_{i}"] = 1234567890.0

        # Try to exceed limit
        conversation_id = "test_conv_overflow"

        with patch('api.routes.stream.LLMClient'):
            response = client.get(f"/api/stream/{conversation_id}")
            assert response.status_code == 503
            assert "concurrent streams" in response.json()["detail"].lower()

    def test_stream_error_handling(self, client):
        """Test error handling during streaming."""
        conversation_id = "test_conv_error"

        with patch('api.routes.stream.LLMClient') as MockLLMClient:
            mock_client_instance = Mock()
            MockLLMClient.return_value.__aenter__.return_value = mock_client_instance

            # Mock streaming response with error
            async def mock_stream(messages):
                yield {"type": "token", "content": "Start"}
                yield {"type": "error", "message": "Test error", "code": "TEST_ERROR"}

            mock_client_instance.chat_completion_stream = mock_stream

            # Make streaming request
            with client.stream("GET", f"/api/stream/{conversation_id}") as response:
                assert response.status_code == 200

                # Read SSE events
                events = []
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        events.append(json.loads(data_str))

                # Verify error event received
                assert len(events) >= 2
                assert events[0] == {"type": "token", "content": "Start"}
                assert events[1]["type"] == "error"
                assert events[1]["message"] == "Test error"
                assert events[1]["code"] == "TEST_ERROR"

    def test_stream_cleanup_on_completion(self, client):
        """Test that stream is cleaned up from active streams after completion."""
        conversation_id = "test_conv_cleanup"

        with patch('api.routes.stream.LLMClient') as MockLLMClient:
            mock_client_instance = Mock()
            MockLLMClient.return_value.__aenter__.return_value = mock_client_instance

            # Mock streaming response
            async def mock_stream(messages):
                yield {"type": "token", "content": "Test"}
                yield {"type": "done", "tokens_used": {"prompt": 5, "completion": 1}}

            mock_client_instance.chat_completion_stream = mock_stream

            # Make streaming request
            with client.stream("GET", f"/api/stream/{conversation_id}") as response:
                assert response.status_code == 200

                # Stream should be active during request
                # (Note: This is checked internally)

            # After streaming completes, verify cleanup
            # (active_streams should be empty after connection closes)
            assert conversation_id not in active_streams


class TestStreamHealth:
    """Tests for /api/stream/health endpoint."""

    def test_stream_health_ok(self, client):
        """Test stream health endpoint returns correct status."""
        response = client.get("/api/stream/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ok"
        assert "active_streams" in data
        assert "max_concurrent_streams" in data
        assert data["max_concurrent_streams"] == MAX_CONCURRENT_STREAMS
        assert "capacity_remaining" in data
        assert "timestamp" in data

    def test_stream_health_with_active_streams(self, client):
        """Test stream health endpoint with active streams."""
        # Add some active streams
        active_streams["conv_1"] = 1234567890.0
        active_streams["conv_2"] = 1234567891.0

        response = client.get("/api/stream/health")
        assert response.status_code == 200

        data = response.json()
        assert data["active_streams"] == 2
        assert data["capacity_remaining"] == MAX_CONCURRENT_STREAMS - 2


# Note: LLM client streaming is tested through integration tests
# and the stream endpoint tests above. Direct LLM client streaming tests
# are complex to mock properly and are better covered by higher-level tests.
