"""
Unit tests for store_memory MCP tool
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, Mock, patch
import httpx

from mcp_server.tools import store_memory_tool_handler, store_memory_tool


class TestStoreMemoryToolHandler:
    """Test store_memory_tool_handler function."""

    @pytest.mark.asyncio
    async def test_store_memory_success(self):
        """Test successful memory storage."""
        # Mock successful HTTP response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "memories_created": 2,
            "ids": ["mem_abc123", "mem_def456"],
            "summary": "User discussed investment strategies"
        }

        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="user123",
                history=[
                    {"role": "user", "content": "Should I invest in AAPL?"},
                    {"role": "assistant", "content": "Based on your risk tolerance..."}
                ],
                metadata={"platform": "telegram", "conversation_id": "conv_123"}
            )

            # Verify result
            assert result["status"] == "success"
            assert result["memories_created"] == 2
            assert result["memory_ids"] == ["mem_abc123", "mem_def456"]
            assert result["summary"] == "User discussed investment strategies"

            # Verify HTTP call
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert "/v1/store" in call_args[0][0]

            # Verify payload structure
            payload = call_args[1]["json"]
            assert payload["user_id"] == "user123"
            assert payload["history"] == [
                {"role": "user", "content": "Should I invest in AAPL?"},
                {"role": "assistant", "content": "Based on your risk tolerance..."}
            ]
            assert payload["metadata"] == {"platform": "telegram", "conversation_id": "conv_123"}

    @pytest.mark.asyncio
    async def test_store_memory_without_metadata(self):
        """Test memory storage without optional metadata."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "memories_created": 1,
            "ids": ["mem_generated"],
            "summary": "Test conversation"
        }

        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="user123",
                history=[{"role": "user", "content": "Hello"}]
            )

            # Verify result
            assert result["status"] == "success"

            # Verify payload doesn't include metadata
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            assert "metadata" not in payload

    @pytest.mark.asyncio
    async def test_store_memory_with_empty_metadata(self):
        """Test memory storage with None metadata."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "memories_created": 1,
            "ids": ["mem_test"],
            "summary": "Test"
        }

        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="user123",
                history=[{"role": "user", "content": "Test message"}],
                metadata=None
            )

            # Verify result
            assert result["status"] == "success"

            # Verify payload doesn't include metadata when None
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            assert "metadata" not in payload

    @pytest.mark.asyncio
    async def test_store_memory_retries_on_server_error(self):
        """Test retry logic on server error (5xx)."""
        # First two attempts fail, third succeeds
        mock_response_fail = Mock()
        mock_response_fail.status_code = 503
        mock_response_fail.json.return_value = {"message": "Service unavailable"}
        mock_response_fail.text = "Service unavailable"

        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {
            "memories_created": 1,
            "ids": ["mem_test"],
            "summary": "Test"
        }

        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            # Fail twice, then succeed
            mock_client.post = AsyncMock(side_effect=[
                mock_response_fail,
                mock_response_fail,
                mock_response_success
            ])
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.asyncio.sleep', new_callable=AsyncMock):
                result = await store_memory_tool_handler(
                    user_id="user123",
                    history=[{"role": "user", "content": "Test"}]
                )

                # Should succeed on third attempt
                assert result["status"] == "success"
                assert mock_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_store_memory_no_retry_on_client_error(self):
        """Test no retry on client error (4xx)."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"message": "Invalid request"}
        mock_response.text = "Invalid request"

        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="user123",
                history=[{"role": "user", "content": "Test"}]
            )

            # Should return error immediately without retry
            assert result["status"] == "error"
            assert result["error_code"] == 400
            assert mock_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_store_memory_retries_on_network_error(self):
        """Test retry logic on network errors."""
        # First two attempts raise network error, third succeeds
        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {
            "memories_created": 1,
            "ids": ["mem_test"],
            "summary": "Test"
        }

        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(side_effect=[
                httpx.ConnectError("Connection refused"),
                httpx.TimeoutException("Timeout"),
                mock_response_success
            ])
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.asyncio.sleep', new_callable=AsyncMock):
                result = await store_memory_tool_handler(
                    user_id="user123",
                    history=[{"role": "user", "content": "Test"}]
                )

                # Should succeed on third attempt
                assert result["status"] == "success"
                assert mock_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_store_memory_fails_after_max_retries(self):
        """Test failure after max retries exceeded."""
        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            # Always raise network error
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.asyncio.sleep', new_callable=AsyncMock):
                result = await store_memory_tool_handler(
                    user_id="user123",
                    history=[{"role": "user", "content": "Test"}]
                )

                # Should fail after 3 attempts
                assert result["status"] == "error"
                assert result["error_code"] == "NETWORK_ERROR"
                assert "3 attempts" in result["message"]
                assert mock_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_store_memory_handles_unexpected_errors(self):
        """Test handling of unexpected errors."""
        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            # Raise unexpected error
            mock_client.post = AsyncMock(side_effect=ValueError("Unexpected error"))
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="user123",
                history=[{"role": "user", "content": "Test"}]
            )

            # Should return error
            assert result["status"] == "error"
            assert result["error_code"] == "INTERNAL_ERROR"
            assert "Unexpected error" in result["message"]

    @pytest.mark.asyncio
    async def test_store_memory_uses_config_url(self):
        """Test that tool uses configured agentic-memories URL."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "memories_created": 1,
            "ids": ["mem_test"],
            "summary": "Test"
        }

        with patch('mcp_server.tools.get_config') as mock_config:
            mock_config.return_value = {"AGENTIC_MEMORIES_URL": "http://custom:9000"}

            with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client

                result = await store_memory_tool_handler(
                    user_id="user123",
                    history=[{"role": "user", "content": "Test"}]
                )

                # Verify custom URL was used
                call_args = mock_client.post.call_args
                assert call_args[0][0].startswith("http://custom:9000")

    @pytest.mark.asyncio
    async def test_store_memory_handles_zero_memories_created(self):
        """Test handling when no memories are extracted."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "memories_created": 0,
            "ids": [],
            "summary": ""
        }

        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="user123",
                history=[{"role": "user", "content": "Hi"}]
            )

            # Should still return success with 0 memories
            assert result["status"] == "success"
            assert result["memories_created"] == 0
            assert result["memory_ids"] == []


class TestStoreMemoryToolSchema:
    """Test store_memory_tool schema definition."""

    def test_tool_has_required_fields(self):
        """Test that tool definition has all required fields."""
        assert "name" in store_memory_tool
        assert "description" in store_memory_tool
        assert "inputSchema" in store_memory_tool
        assert "handler" in store_memory_tool

    def test_tool_name(self):
        """Test tool name."""
        assert store_memory_tool["name"] == "store_memory"

    def test_tool_description_not_empty(self):
        """Test tool has non-empty description."""
        assert len(store_memory_tool["description"]) > 0
        assert "agentic-memories" in store_memory_tool["description"]

    def test_tool_handler_is_callable(self):
        """Test that handler is callable."""
        assert callable(store_memory_tool["handler"])
        assert store_memory_tool["handler"] == store_memory_tool_handler

    def test_input_schema_structure(self):
        """Test input schema structure."""
        schema = store_memory_tool["inputSchema"]
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema

    def test_input_schema_required_fields(self):
        """Test input schema required fields."""
        schema = store_memory_tool["inputSchema"]
        required = schema["required"]
        assert "user_id" in required
        assert "history" in required

    def test_input_schema_properties(self):
        """Test input schema properties."""
        properties = store_memory_tool["inputSchema"]["properties"]

        # Check all expected properties exist
        assert "user_id" in properties
        assert "history" in properties
        assert "metadata" in properties

        # Check types
        assert properties["user_id"]["type"] == "string"
        assert properties["history"]["type"] == "array"
        assert properties["metadata"]["type"] == "object"

    def test_input_schema_history_structure(self):
        """Test history array schema structure."""
        history = store_memory_tool["inputSchema"]["properties"]["history"]
        assert history["type"] == "array"
        assert "items" in history

        item_schema = history["items"]
        assert item_schema["type"] == "object"
        assert "properties" in item_schema
        assert "required" in item_schema

        # Check message properties
        assert "role" in item_schema["properties"]
        assert "content" in item_schema["properties"]

        # Check role enum
        role_prop = item_schema["properties"]["role"]
        assert role_prop["type"] == "string"
        assert "enum" in role_prop
        assert "user" in role_prop["enum"]
        assert "assistant" in role_prop["enum"]
        assert "system" in role_prop["enum"]

        # Check required fields
        assert "role" in item_schema["required"]
        assert "content" in item_schema["required"]

    def test_input_schema_metadata_structure(self):
        """Test metadata object schema structure."""
        metadata = store_memory_tool["inputSchema"]["properties"]["metadata"]
        assert metadata["type"] == "object"
        assert "properties" in metadata

        # Check metadata properties
        assert "platform" in metadata["properties"]
        assert "conversation_id" in metadata["properties"]

        # Check types
        assert metadata["properties"]["platform"]["type"] == "string"
        assert metadata["properties"]["conversation_id"]["type"] == "string"
