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
            "status": "success",
            "memory_id": "mem_abc123",
            "stored_at": "2025-11-11T10:00:00Z"
        }

        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="user123",
                conversation_summary="User asked for investment advice",
                decisions=[
                    {
                        "decision": "Buy AAPL",
                        "options_considered": ["AAPL", "MSFT"],
                        "reasoning": "Strong fundamentals",
                        "outcome": None
                    }
                ],
                preferences={
                    "risk_tolerance": "moderate",
                    "priorities": ["growth"],
                    "constraints": []
                },
                topics=["investing", "stocks"],
                sentiment="positive"
            )

            # Verify result
            assert result["status"] == "success"
            assert result["memory_id"] == "mem_abc123"

            # Verify HTTP call
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert "/memories" in call_args[0][0]

            # Verify payload structure
            payload = call_args[1]["json"]
            assert payload["user_id"] == "user123"
            assert "memory" in payload
            assert payload["memory"]["conversation_summary"] == "User asked for investment advice"

    @pytest.mark.asyncio
    async def test_store_memory_auto_generates_memory_id(self):
        """Test that memory_id is auto-generated if not provided."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "memory_id": "mem_generated",
            "stored_at": "2025-11-11T10:00:00Z"
        }

        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="user123",
                conversation_summary="Test summary"
            )

            # Verify memory_id was generated
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            assert payload["memory"]["memory_id"].startswith("mem_")

    @pytest.mark.asyncio
    async def test_store_memory_auto_generates_timestamp(self):
        """Test that timestamp is auto-generated if not provided."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "memory_id": "mem_test",
            "stored_at": "2025-11-11T10:00:00Z"
        }

        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="user123",
                conversation_summary="Test summary"
            )

            # Verify timestamp was generated
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            assert "timestamp" in payload["memory"]
            assert payload["memory"]["timestamp"].endswith("Z")

    @pytest.mark.asyncio
    async def test_store_memory_defaults_optional_fields(self):
        """Test that optional fields default to empty values."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "memory_id": "mem_test",
            "stored_at": "2025-11-11T10:00:00Z"
        }

        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="user123",
                conversation_summary="Test summary"
                # No decisions, preferences, topics, sentiment
            )

            # Verify defaults
            call_args = mock_client.post.call_args
            memory = call_args[1]["json"]["memory"]
            assert memory["decisions"] == []
            assert memory["preferences"] == {}
            assert memory["topics"] == []
            assert memory["sentiment"] is None

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
            "status": "success",
            "memory_id": "mem_test",
            "stored_at": "2025-11-11T10:00:00Z"
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
                    conversation_summary="Test summary"
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
                conversation_summary="Test summary"
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
            "status": "success",
            "memory_id": "mem_test",
            "stored_at": "2025-11-11T10:00:00Z"
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
                    conversation_summary="Test summary"
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
                    conversation_summary="Test summary"
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
                conversation_summary="Test summary"
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
            "status": "success",
            "memory_id": "mem_test",
            "stored_at": "2025-11-11T10:00:00Z"
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
                    conversation_summary="Test summary"
                )

                # Verify custom URL was used
                call_args = mock_client.post.call_args
                assert call_args[0][0].startswith("http://custom:9000")


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
        assert "conversation_summary" in required

    def test_input_schema_properties(self):
        """Test input schema properties."""
        properties = store_memory_tool["inputSchema"]["properties"]

        # Check all expected properties exist
        assert "user_id" in properties
        assert "conversation_summary" in properties
        assert "decisions" in properties
        assert "preferences" in properties
        assert "topics" in properties
        assert "sentiment" in properties
        assert "memory_id" in properties
        assert "timestamp" in properties

        # Check types
        assert properties["user_id"]["type"] == "string"
        assert properties["conversation_summary"]["type"] == "string"
        assert properties["decisions"]["type"] == "array"
        assert properties["preferences"]["type"] == "object"
        assert properties["topics"]["type"] == "array"
        assert properties["sentiment"]["type"] == "string"

    def test_input_schema_decisions_structure(self):
        """Test decisions array schema structure."""
        decisions = store_memory_tool["inputSchema"]["properties"]["decisions"]
        assert decisions["type"] == "array"
        assert "items" in decisions

        item_schema = decisions["items"]
        assert item_schema["type"] == "object"
        assert "properties" in item_schema
        assert "required" in item_schema

        # Check decision properties
        assert "decision" in item_schema["properties"]
        assert "options_considered" in item_schema["properties"]
        assert "reasoning" in item_schema["properties"]
        assert "outcome" in item_schema["properties"]

        # Check required fields
        assert "decision" in item_schema["required"]
        assert "options_considered" in item_schema["required"]
        assert "reasoning" in item_schema["required"]

    def test_input_schema_preferences_structure(self):
        """Test preferences object schema structure."""
        preferences = store_memory_tool["inputSchema"]["properties"]["preferences"]
        assert preferences["type"] == "object"
        assert "properties" in preferences

        # Check preference properties
        assert "risk_tolerance" in preferences["properties"]
        assert "priorities" in preferences["properties"]
        assert "constraints" in preferences["properties"]

        # Check types
        assert preferences["properties"]["risk_tolerance"]["type"] == "string"
        assert preferences["properties"]["priorities"]["type"] == "array"
        assert preferences["properties"]["constraints"]["type"] == "array"
