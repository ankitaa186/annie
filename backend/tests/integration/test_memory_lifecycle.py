"""
Unit tests for memory lifecycle operations (mocked).

Tests error recovery and mocked lifecycle operations without requiring
external services. Live integration tests are in e2e/test_memory_lifecycle_live.py.
"""

import pytest
import httpx
from unittest.mock import AsyncMock, Mock, patch

# Import MCP tools for direct testing
import sys
from pathlib import Path

# Add mcp_server to path for imports - try multiple possible locations
mcp_server_paths = [
    Path(__file__).parent.parent.parent.parent / "mcp_server",  # Local dev
    Path(__file__).resolve().parent.parent.parent.parent / "mcp_server",  # Resolved path
    Path.cwd() / "mcp_server",  # From repo root
]

for mcp_path in mcp_server_paths:
    if mcp_path.exists():
        sys.path.insert(0, str(mcp_path.parent))
        break

try:
    from mcp_server.tools import (
        store_memory_tool_handler,
        delete_memory_tool_handler,
        retrieve_memories_tool_handler
    )
    MCP_TOOLS_AVAILABLE = True
except ImportError:
    MCP_TOOLS_AVAILABLE = False
    store_memory_tool_handler = None
    delete_memory_tool_handler = None
    retrieve_memories_tool_handler = None

# Skip entire module if MCP tools are not available
if not MCP_TOOLS_AVAILABLE:
    pytest.skip("mcp_server module not available", allow_module_level=True)

# Test constants
TEST_USER_ID = "test_user_epic14"


class TestErrorRecovery:
    """Tests for error recovery scenarios (mocked - no service required)."""

    @pytest.mark.asyncio
    async def test_store_memory_recovers_after_transient_failure(self):
        """Test error recovery after transient failures (AC #3)."""
        # Mock transient failure followed by success
        mock_response_fail = Mock()
        mock_response_fail.status_code = 503
        mock_response_fail.json.return_value = {
            "status": "error",
            "message": "Service temporarily unavailable",
            "error_code": "STORAGE_ERROR"
        }

        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {
            "status": "success",
            "memory_id": "mem_recovered",
            "storage": {"chromadb": True}
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(side_effect=[
                mock_response_fail,  # First attempt fails
                mock_response_success  # Second attempt succeeds
            ])
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.memory.asyncio.sleep', new_callable=AsyncMock):
                result = await store_memory_tool_handler(
                    user_id=TEST_USER_ID,
                    content="Recovery test memory"
                )

                # Should succeed after retry
                assert result["status"] == "success"
                assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_delete_memory_handles_service_restart(self):
        """Test delete handles service restart gracefully."""
        # First call fails with network error, simulating service restart
        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.delete = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock_client_class.return_value = mock_client

            result = await delete_memory_tool_handler(
                user_id=TEST_USER_ID,
                memory_id="mem_test",
                reason="Service restart test"
            )

            # Should return clean error, not crash
            assert result["status"] == "error"
            assert result["deleted"] is False
            assert "Connection refused" in result["message"]


class TestMockedLifecycle:
    """Mocked integration tests that don't require real service."""

    @pytest.mark.asyncio
    async def test_store_success_mocked(self):
        """Test store with mocked response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "memory_id": "mem_mocked_123",
            "message": "Memory stored",
            "storage": {"chromadb": True, "episodic": False, "emotional": False, "procedural": False}
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="test_user",
                content="Mocked lifecycle test"
            )

            assert result["status"] == "success"
            assert result["memory_id"] == "mem_mocked_123"

    @pytest.mark.asyncio
    async def test_retrieve_success_mocked(self):
        """Test retrieve with mocked response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [{"id": "mem_123", "content": "Test memory", "score": 0.95}],
            "count": 1
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            # retrieve_memories uses GET, not POST
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await retrieve_memories_tool_handler(
                user_id="test_user",
                query="test memory"
            )

            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_delete_success_mocked(self):
        """Test delete with mocked response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"deleted": True}

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.delete = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await delete_memory_tool_handler(
                user_id="test_user",
                memory_id="mem_123",
                reason="Mocked test cleanup"
            )

            assert result["status"] == "success"
            assert result["deleted"] is True

    @pytest.mark.asyncio
    async def test_full_mocked_lifecycle(self):
        """Test full lifecycle with separate mocked operations."""
        # Store
        mock_store_response = Mock()
        mock_store_response.status_code = 200
        mock_store_response.json.return_value = {
            "status": "success",
            "memory_id": "mem_lifecycle_123",
            "storage": {"chromadb": True}
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_store_response)
            mock_client_class.return_value = mock_client

            store_result = await store_memory_tool_handler(
                user_id="test_user",
                content="Full lifecycle test"
            )
            assert store_result["status"] == "success"
            memory_id = store_result["memory_id"]

        # Retrieve
        mock_retrieve_response = Mock()
        mock_retrieve_response.status_code = 200
        mock_retrieve_response.json.return_value = {
            "results": [{"id": memory_id, "content": "Full lifecycle test", "score": 0.9}],
            "count": 1
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            # retrieve_memories uses GET, not POST
            mock_client.get = AsyncMock(return_value=mock_retrieve_response)
            mock_client_class.return_value = mock_client

            retrieve_result = await retrieve_memories_tool_handler(
                user_id="test_user",
                query="lifecycle test"
            )
            assert retrieve_result["status"] == "success"

        # Delete
        mock_delete_response = Mock()
        mock_delete_response.status_code = 200
        mock_delete_response.json.return_value = {"deleted": True}

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.delete = AsyncMock(return_value=mock_delete_response)
            mock_client_class.return_value = mock_client

            delete_result = await delete_memory_tool_handler(
                user_id="test_user",
                memory_id=memory_id,
                reason="Lifecycle test cleanup"
            )
            assert delete_result["status"] == "success"
            assert delete_result["deleted"] is True
