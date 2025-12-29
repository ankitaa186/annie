"""
Unit tests for delete_memory MCP tool

Story 14.3: Add delete_memory Tool
- Tests the delete_memory_tool_handler function
- Tests all response code handling (200, 403, 404, 500, timeout)
- Tests audit logging with reason field
- Tests tool schema definition
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, Mock, patch
import httpx

from mcp_server.tools import delete_memory_tool_handler, delete_memory_tool


class TestDeleteMemoryToolHandler:
    """Test delete_memory_tool_handler function."""

    @pytest.mark.asyncio
    async def test_delete_memory_success(self):
        """Test successful memory deletion (AC #3)."""
        # Mock successful HTTP response with deleted: true
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "deleted": True,
            "memory_id": "mem_abc123",
            "storage": {
                "chromadb": True,
                "episodic": True,
                "emotional": False,
                "procedural": False
            }
        }

        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.delete = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await delete_memory_tool_handler(
                user_id="user123",
                memory_id="mem_abc123",
                reason="User correction"
            )

            # Verify result structure (AC #3)
            assert result["status"] == "success"
            assert result["deleted"] is True
            assert result["memory_id"] == "mem_abc123"
            assert result["message"] == "Memory deleted successfully"

            # Verify correct endpoint was called (AC #2)
            mock_client.delete.assert_called_once()
            call_args = mock_client.delete.call_args
            assert "/v1/memories/mem_abc123" in call_args[0][0]
            assert call_args[1]["params"]["user_id"] == "user123"

    @pytest.mark.asyncio
    async def test_delete_memory_not_found_deleted_false(self):
        """Test memory not found response with deleted: false (AC #4)."""
        # Mock 200 response with deleted: false
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "error",
            "deleted": False,
            "memory_id": "mem_abc123",
            "message": "Memory not found"
        }

        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.delete = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await delete_memory_tool_handler(
                user_id="user123",
                memory_id="mem_abc123"
            )

            # Verify error response (AC #4)
            assert result["status"] == "error"
            assert result["deleted"] is False
            assert result["memory_id"] == "mem_abc123"
            assert "not found" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_delete_memory_unauthorized_403(self):
        """Test unauthorized delete attempt (AC #5)."""
        # Mock 403 response
        mock_response = Mock()
        mock_response.status_code = 403

        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.delete = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await delete_memory_tool_handler(
                user_id="user123",
                memory_id="mem_abc123"
            )

            # Verify unauthorized response (AC #5)
            assert result["status"] == "error"
            assert result["deleted"] is False
            assert result["memory_id"] == "mem_abc123"
            assert "unauthorized" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_delete_memory_not_found_404(self):
        """Test memory not found response with 404 status."""
        # Mock 404 response
        mock_response = Mock()
        mock_response.status_code = 404

        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.delete = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await delete_memory_tool_handler(
                user_id="user123",
                memory_id="mem_abc123"
            )

            # Verify not found response
            assert result["status"] == "error"
            assert result["deleted"] is False
            assert result["memory_id"] == "mem_abc123"
            assert "not found" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_delete_memory_server_error_500(self):
        """Test server error response (AC #6)."""
        # Mock 500 response
        mock_response = Mock()
        mock_response.status_code = 500

        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.delete = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await delete_memory_tool_handler(
                user_id="user123",
                memory_id="mem_abc123"
            )

            # Verify error response with status code (AC #6)
            assert result["status"] == "error"
            assert result["deleted"] is False
            assert result["memory_id"] == "mem_abc123"
            assert "500" in result["message"]

    @pytest.mark.asyncio
    async def test_delete_memory_timeout(self):
        """Test timeout handling (AC #7)."""
        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.delete = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_client_class.return_value = mock_client

            result = await delete_memory_tool_handler(
                user_id="user123",
                memory_id="mem_abc123"
            )

            # Verify timeout response (AC #7)
            assert result["status"] == "error"
            assert result["deleted"] is False
            assert result["memory_id"] == "mem_abc123"
            assert "timed out" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_delete_memory_uses_10s_timeout(self):
        """Test that 10 second timeout is used (AC #2)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"deleted": True}

        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.delete = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await delete_memory_tool_handler(
                user_id="user123",
                memory_id="mem_abc123"
            )

            # Verify 10s timeout (AC #2)
            mock_client_class.assert_called_once_with(timeout=10.0)

    @pytest.mark.asyncio
    async def test_delete_memory_unexpected_exception(self):
        """Test handling of unexpected exceptions."""
        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.delete = AsyncMock(side_effect=Exception("Network error"))
            mock_client_class.return_value = mock_client

            result = await delete_memory_tool_handler(
                user_id="user123",
                memory_id="mem_abc123"
            )

            # Verify error response
            assert result["status"] == "error"
            assert result["deleted"] is False
            assert result["memory_id"] == "mem_abc123"
            assert "Network error" in result["message"]

    @pytest.mark.asyncio
    async def test_delete_memory_logging_success(self):
        """Test audit logging on success (AC #8)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"deleted": True}

        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.delete = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.logger') as mock_logger:
                await delete_memory_tool_handler(
                    user_id="user123",
                    memory_id="mem_abc123",
                    reason="User correction"
                )

                # Verify audit logging includes required fields (AC #8)
                mock_logger.info.assert_called()
                call_args = mock_logger.info.call_args
                extra = call_args[1]["extra"]
                assert extra["user_id"] == "user123"
                assert extra["memory_id"] == "mem_abc123"
                assert extra["reason"] == "User correction"
                assert "duration_ms" in extra

    @pytest.mark.asyncio
    async def test_delete_memory_logging_error(self):
        """Test audit logging on error (AC #8)."""
        mock_response = Mock()
        mock_response.status_code = 500

        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.delete = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.logger') as mock_logger:
                await delete_memory_tool_handler(
                    user_id="user123",
                    memory_id="mem_abc123",
                    reason="Test deletion"
                )

                # Verify error logging includes required fields (AC #8)
                mock_logger.error.assert_called()
                call_args = mock_logger.error.call_args
                extra = call_args[1]["extra"]
                assert extra["user_id"] == "user123"
                assert extra["memory_id"] == "mem_abc123"
                assert extra["reason"] == "Test deletion"
                assert "duration_ms" in extra

    @pytest.mark.asyncio
    async def test_delete_memory_without_reason(self):
        """Test deletion without reason parameter."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"deleted": True}

        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.delete = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await delete_memory_tool_handler(
                user_id="user123",
                memory_id="mem_abc123"
                # No reason provided
            )

            # Should still succeed
            assert result["status"] == "success"
            assert result["deleted"] is True

    @pytest.mark.asyncio
    async def test_delete_memory_uses_config_url(self):
        """Test that agentic-memories URL is read from config."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"deleted": True}

        with patch('mcp_server.tools.get_config') as mock_get_config:
            mock_get_config.return_value = {
                "AGENTIC_MEMORIES_URL": "http://custom-host:9999"
            }

            with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.delete = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client

                await delete_memory_tool_handler(
                    user_id="user123",
                    memory_id="mem_abc123"
                )

                # Verify custom URL was used
                call_args = mock_client.delete.call_args
                assert "http://custom-host:9999" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_delete_memory_config_failure_uses_default(self):
        """Test that default URL is used when config fails."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"deleted": True}

        with patch('mcp_server.tools.get_config') as mock_get_config:
            mock_get_config.side_effect = Exception("Config error")

            with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.delete = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client

                await delete_memory_tool_handler(
                    user_id="user123",
                    memory_id="mem_abc123"
                )

                # Verify default URL was used
                call_args = mock_client.delete.call_args
                assert "host.docker.internal:8080" in call_args[0][0]


class TestDeleteMemoryToolSchema:
    """Test delete_memory_tool schema definition (AC #1, AC #9)."""

    def test_tool_has_required_fields(self):
        """Test that tool definition has all required fields."""
        assert "name" in delete_memory_tool
        assert "description" in delete_memory_tool
        assert "inputSchema" in delete_memory_tool
        assert "handler" in delete_memory_tool

    def test_tool_name(self):
        """Test tool name."""
        assert delete_memory_tool["name"] == "delete_memory"

    def test_tool_description_includes_guidance(self):
        """Test tool description includes usage guidance for LLM (AC #1)."""
        desc = delete_memory_tool["description"]
        # Should mention when to use
        assert "forget" in desc.lower() or "delete" in desc.lower()
        # Should mention workflow
        assert "retrieve_memories" in desc
        # Should mention confirmation
        assert "confirm" in desc.lower()
        # Should mention cannot be undone
        assert "cannot be undone" in desc.lower() or "undone" in desc.lower()

    def test_tool_handler_is_callable(self):
        """Test tool handler is callable."""
        assert callable(delete_memory_tool["handler"])
        assert delete_memory_tool["handler"] == delete_memory_tool_handler

    def test_input_schema_structure(self):
        """Test input schema structure (AC #1)."""
        schema = delete_memory_tool["inputSchema"]
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema

    def test_input_schema_required_fields(self):
        """Test required fields are user_id and memory_id (AC #1)."""
        schema = delete_memory_tool["inputSchema"]
        required = schema["required"]
        assert "user_id" in required
        assert "memory_id" in required
        # reason should NOT be required
        assert "reason" not in required

    def test_input_schema_user_id_property(self):
        """Test user_id property definition (AC #1)."""
        schema = delete_memory_tool["inputSchema"]
        user_id_prop = schema["properties"]["user_id"]
        assert user_id_prop["type"] == "string"
        assert "description" in user_id_prop

    def test_input_schema_memory_id_property(self):
        """Test memory_id property definition (AC #1)."""
        schema = delete_memory_tool["inputSchema"]
        memory_id_prop = schema["properties"]["memory_id"]
        assert memory_id_prop["type"] == "string"
        assert "description" in memory_id_prop
        # Should mention retrieve_memories
        assert "retrieve_memories" in memory_id_prop["description"].lower() or "retrieve" in memory_id_prop["description"].lower()

    def test_input_schema_reason_property(self):
        """Test reason property definition (AC #1)."""
        schema = delete_memory_tool["inputSchema"]
        reason_prop = schema["properties"]["reason"]
        assert reason_prop["type"] == "string"
        assert "description" in reason_prop
        # Should mention audit
        assert "audit" in reason_prop["description"].lower()
