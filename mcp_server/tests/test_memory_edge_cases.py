"""
Edge case tests for memory tools.

Story 14.6: Integration Testing & Validation - AC #4
Tests edge case inputs for store_memory and delete_memory tools:
- Empty content field handling
- Content at max length (5000 chars)
- Content exceeding max length
- Persona tags limits (10, 11 tags)
- Importance validation (boundary values, invalid values)
- Valence validation (boundary values, invalid values)
- Arousal validation (boundary values, invalid values)
- Missing required fields
- Service unavailable scenarios
- Connection timeout scenarios
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
import httpx

from mcp_server.tools import (
    store_memory_tool_handler,
    store_memory_tool,
    delete_memory_tool_handler,
    delete_memory_tool
)


class TestStoreMemoryEdgeCases:
    """Edge case tests for store_memory tool (AC #4)."""

    @pytest.mark.asyncio
    async def test_empty_content_field(self):
        """Test empty content field handling."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "status": "error",
            "message": "Content cannot be empty",
            "error_code": "VALIDATION_ERROR"
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="test_user",
                content=""  # Empty content
            )

            assert result["status"] == "error"
            assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_content_at_exactly_5000_chars(self):
        """Test content at exactly 5000 characters (valid boundary)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "memory_id": "mem_max_length",
            "storage": {"chromadb": True}
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            # Generate exactly 5000 characters
            content_5000 = "A" * 5000

            result = await store_memory_tool_handler(
                user_id="test_user",
                content=content_5000
            )

            assert result["status"] == "success"
            # Verify payload was sent with full content
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            assert len(payload["content"]) == 5000

    @pytest.mark.asyncio
    async def test_content_exceeding_5000_chars_rejected(self):
        """Test content exceeding 5000 characters is rejected by service."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "status": "error",
            "message": "Content exceeds maximum length of 5000 characters",
            "error_code": "VALIDATION_ERROR"
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            # Content exceeding max
            content_5001 = "A" * 5001

            result = await store_memory_tool_handler(
                user_id="test_user",
                content=content_5001
            )

            assert result["status"] == "error"
            assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_10_persona_tags_works(self):
        """Test 10 persona_tags (maximum allowed) works correctly."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "memory_id": "mem_10_tags",
            "storage": {"chromadb": True}
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            tags = [f"tag{i}" for i in range(10)]

            result = await store_memory_tool_handler(
                user_id="test_user",
                content="Test with 10 tags",
                persona_tags=tags
            )

            assert result["status"] == "success"
            payload = mock_client.post.call_args[1]["json"]
            assert len(payload["persona_tags"]) == 10

    @pytest.mark.asyncio
    async def test_11_persona_tags_truncated(self):
        """Test 11 persona_tags is truncated to 10."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "memory_id": "mem_truncated_tags",
            "storage": {"chromadb": True}
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            tags = [f"tag{i}" for i in range(11)]  # 11 tags

            result = await store_memory_tool_handler(
                user_id="test_user",
                content="Test with 11 tags",
                persona_tags=tags
            )

            assert result["status"] == "success"
            payload = mock_client.post.call_args[1]["json"]
            assert len(payload["persona_tags"]) == 10  # Truncated
            assert payload["persona_tags"] == tags[:10]  # First 10 tags

    @pytest.mark.asyncio
    async def test_importance_0_0_valid_boundary(self):
        """Test importance = 0.0 (valid lower boundary)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "memory_id": "mem_imp_0",
            "storage": {"chromadb": True}
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="test_user",
                content="Test importance boundary",
                importance=0.0
            )

            assert result["status"] == "success"
            payload = mock_client.post.call_args[1]["json"]
            assert payload["importance"] == 0.0

    @pytest.mark.asyncio
    async def test_importance_1_0_valid_boundary(self):
        """Test importance = 1.0 (valid upper boundary)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "memory_id": "mem_imp_1",
            "storage": {"chromadb": True}
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="test_user",
                content="Test importance boundary",
                importance=1.0
            )

            assert result["status"] == "success"
            payload = mock_client.post.call_args[1]["json"]
            assert payload["importance"] == 1.0

    @pytest.mark.asyncio
    async def test_importance_negative_rejected(self):
        """Test importance = -0.1 (invalid - below minimum)."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "status": "error",
            "message": "Importance must be between 0.0 and 1.0",
            "error_code": "VALIDATION_ERROR"
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="test_user",
                content="Test invalid importance",
                importance=-0.1  # Invalid
            )

            # Service should reject, not retry
            assert result["status"] == "error"
            assert result["error_code"] == "VALIDATION_ERROR"
            assert mock_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_importance_above_1_rejected(self):
        """Test importance = 1.1 (invalid - above maximum)."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "status": "error",
            "message": "Importance must be between 0.0 and 1.0",
            "error_code": "VALIDATION_ERROR"
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="test_user",
                content="Test invalid importance",
                importance=1.1  # Invalid
            )

            assert result["status"] == "error"
            assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_valence_negative_1_valid_boundary(self):
        """Test valence = -1.0 (valid lower boundary)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "memory_id": "mem_valence_neg",
            "storage": {"chromadb": True, "emotional": True}
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="test_user",
                content="Test valence boundary",
                emotional_state="sad",
                valence=-1.0
            )

            assert result["status"] == "success"
            payload = mock_client.post.call_args[1]["json"]
            assert payload["valence"] == -1.0

    @pytest.mark.asyncio
    async def test_valence_positive_1_valid_boundary(self):
        """Test valence = 1.0 (valid upper boundary)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "memory_id": "mem_valence_pos",
            "storage": {"chromadb": True, "emotional": True}
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="test_user",
                content="Test valence boundary",
                emotional_state="joyful",
                valence=1.0
            )

            assert result["status"] == "success"
            payload = mock_client.post.call_args[1]["json"]
            assert payload["valence"] == 1.0

    @pytest.mark.asyncio
    async def test_valence_below_negative_1_rejected(self):
        """Test valence = -1.1 (invalid - below minimum)."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "status": "error",
            "message": "Valence must be between -1.0 and 1.0",
            "error_code": "VALIDATION_ERROR"
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="test_user",
                content="Test invalid valence",
                emotional_state="test",
                valence=-1.1  # Invalid
            )

            assert result["status"] == "error"
            assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_valence_above_1_rejected(self):
        """Test valence = 1.1 (invalid - above maximum)."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "status": "error",
            "message": "Valence must be between -1.0 and 1.0",
            "error_code": "VALIDATION_ERROR"
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="test_user",
                content="Test invalid valence",
                emotional_state="test",
                valence=1.1  # Invalid
            )

            assert result["status"] == "error"
            assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_arousal_0_0_valid_boundary(self):
        """Test arousal = 0.0 (valid lower boundary)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "memory_id": "mem_arousal_0",
            "storage": {"chromadb": True, "emotional": True}
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="test_user",
                content="Test arousal boundary",
                emotional_state="calm",
                arousal=0.0
            )

            assert result["status"] == "success"
            payload = mock_client.post.call_args[1]["json"]
            assert payload["arousal"] == 0.0

    @pytest.mark.asyncio
    async def test_arousal_1_0_valid_boundary(self):
        """Test arousal = 1.0 (valid upper boundary)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "memory_id": "mem_arousal_1",
            "storage": {"chromadb": True, "emotional": True}
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="test_user",
                content="Test arousal boundary",
                emotional_state="excited",
                arousal=1.0
            )

            assert result["status"] == "success"
            payload = mock_client.post.call_args[1]["json"]
            assert payload["arousal"] == 1.0

    @pytest.mark.asyncio
    async def test_arousal_negative_rejected(self):
        """Test arousal = -0.1 (invalid - below minimum)."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "status": "error",
            "message": "Arousal must be between 0.0 and 1.0",
            "error_code": "VALIDATION_ERROR"
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="test_user",
                content="Test invalid arousal",
                emotional_state="test",
                arousal=-0.1  # Invalid
            )

            assert result["status"] == "error"
            assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_arousal_above_1_rejected(self):
        """Test arousal = 1.1 (invalid - above maximum)."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "status": "error",
            "message": "Arousal must be between 0.0 and 1.0",
            "error_code": "VALIDATION_ERROR"
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="test_user",
                content="Test invalid arousal",
                emotional_state="test",
                arousal=1.1  # Invalid
            )

            assert result["status"] == "error"
            assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_service_unavailable_503(self):
        """Test service unavailable (503) returns clean error message."""
        mock_response = Mock()
        mock_response.status_code = 503
        mock_response.json.return_value = {"message": "Service unavailable"}
        mock_response.text = "Service unavailable"

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.memory.asyncio.sleep', new_callable=AsyncMock):
                result = await store_memory_tool_handler(
                    user_id="test_user",
                    content="Test service unavailable"
                )

                # Should retry and eventually fail with clean message
                assert result["status"] == "error"
                assert "503" in result["message"] or "unavailable" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_connection_timeout_clean_error(self):
        """Test connection timeout returns clean error message."""
        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(
                side_effect=httpx.TimeoutException("Connection timed out")
            )
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.memory.asyncio.sleep', new_callable=AsyncMock):
                result = await store_memory_tool_handler(
                    user_id="test_user",
                    content="Test timeout"
                )

                assert result["status"] == "error"
                assert result["error_code"] == "TIMEOUT_ERROR"
                assert "10s timeout" in result["message"]


class TestDeleteMemoryEdgeCases:
    """Edge case tests for delete_memory tool (AC #4)."""

    @pytest.mark.asyncio
    async def test_missing_memory_id_schema_validation(self):
        """Test that schema requires memory_id."""
        schema = delete_memory_tool["inputSchema"]
        required = schema["required"]
        assert "memory_id" in required

    @pytest.mark.asyncio
    async def test_missing_user_id_schema_validation(self):
        """Test that schema requires user_id."""
        schema = delete_memory_tool["inputSchema"]
        required = schema["required"]
        assert "user_id" in required

    @pytest.mark.asyncio
    async def test_service_unavailable_503_delete(self):
        """Test service unavailable (503) on delete."""
        mock_response = Mock()
        mock_response.status_code = 503

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.delete = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await delete_memory_tool_handler(
                user_id="test_user",
                memory_id="mem_test"
            )

            assert result["status"] == "error"
            assert result["deleted"] is False
            assert "503" in result["message"]

    @pytest.mark.asyncio
    async def test_connection_timeout_delete(self):
        """Test connection timeout on delete."""
        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.delete = AsyncMock(
                side_effect=httpx.TimeoutException("Connection timed out")
            )
            mock_client_class.return_value = mock_client

            result = await delete_memory_tool_handler(
                user_id="test_user",
                memory_id="mem_test"
            )

            assert result["status"] == "error"
            assert result["deleted"] is False
            assert "timed out" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_network_error_delete(self):
        """Test network error on delete."""
        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.delete = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock_client_class.return_value = mock_client

            result = await delete_memory_tool_handler(
                user_id="test_user",
                memory_id="mem_test"
            )

            assert result["status"] == "error"
            assert result["deleted"] is False
            assert "Connection refused" in result["message"]


class TestSchemaValidation:
    """Tests for JSON schema validation definitions."""

    def test_store_memory_schema_content_maxlength(self):
        """Test content maxLength is 5000 in schema."""
        schema = store_memory_tool["inputSchema"]
        content_prop = schema["properties"]["content"]
        assert content_prop["maxLength"] == 5000

    def test_store_memory_schema_persona_tags_maxitems(self):
        """Test persona_tags maxItems is 10 in schema."""
        schema = store_memory_tool["inputSchema"]
        tags_prop = schema["properties"]["persona_tags"]
        assert tags_prop["maxItems"] == 10

    def test_store_memory_schema_importance_range(self):
        """Test importance range is 0.0-1.0 in schema."""
        schema = store_memory_tool["inputSchema"]
        importance_prop = schema["properties"]["importance"]
        assert importance_prop["minimum"] == 0.0
        assert importance_prop["maximum"] == 1.0

    def test_store_memory_schema_valence_range(self):
        """Test valence range is -1.0 to 1.0 in schema."""
        schema = store_memory_tool["inputSchema"]
        valence_prop = schema["properties"]["valence"]
        assert valence_prop["minimum"] == -1.0
        assert valence_prop["maximum"] == 1.0

    def test_store_memory_schema_arousal_range(self):
        """Test arousal range is 0.0-1.0 in schema."""
        schema = store_memory_tool["inputSchema"]
        arousal_prop = schema["properties"]["arousal"]
        assert arousal_prop["minimum"] == 0.0
        assert arousal_prop["maximum"] == 1.0

    def test_store_memory_schema_layer_enum(self):
        """Test layer enum values in schema."""
        schema = store_memory_tool["inputSchema"]
        layer_prop = schema["properties"]["layer"]
        assert set(layer_prop["enum"]) == {"short-term", "semantic", "long-term"}

    def test_store_memory_schema_proficiency_enum(self):
        """Test proficiency_level enum values in schema."""
        schema = store_memory_tool["inputSchema"]
        prof_prop = schema["properties"]["proficiency_level"]
        assert set(prof_prop["enum"]) == {"beginner", "intermediate", "advanced", "expert"}

    def test_delete_memory_schema_required_fields(self):
        """Test delete_memory required fields."""
        schema = delete_memory_tool["inputSchema"]
        required = schema["required"]
        assert "user_id" in required
        assert "memory_id" in required
        assert "reason" not in required  # Optional
