"""
Unit tests for store_memory MCP tool

Story 14.2: Update store_memory Tool Handler
- Tests the updated handler using /v1/memories/direct endpoint
- Tests new payload structure with type, confidence, and merged metadata
- Tests new response format with storage details
- Tests error code handling (VALIDATION_ERROR, EMBEDDING_ERROR, etc.)
- Tests 10s timeout
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
import httpx

from mcp_server.tools import store_memory_tool_handler, store_memory_tool


class TestStoreMemoryToolHandler:
    """Test store_memory_tool_handler function."""

    @pytest.mark.asyncio
    async def test_store_memory_success_minimal(self):
        """Test successful memory storage with minimal required fields."""
        # Mock successful HTTP response with new format
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "memory_id": "mem_abc123",
            "message": "Memory stored successfully",
            "storage": {
                "chromadb": True,
                "episodic": False,
                "emotional": False,
                "procedural": False
            }
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="user123",
                content="User is allergic to shellfish"
            )

            # Verify result includes storage details (AC #4)
            assert result["status"] == "success"
            assert result["memory_id"] == "mem_abc123"
            assert result["message"] == "Memory stored successfully"
            assert result["storage"]["chromadb"] is True
            assert result["content"] == "User is allergic to shellfish"

            # Verify HTTP call uses new endpoint (AC #1)
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert "/v1/memories/direct" in call_args[0][0]

            # Verify payload structure with new fields (AC #3)
            payload = call_args[1]["json"]
            assert payload["user_id"] == "user123"
            assert payload["content"] == "User is allergic to shellfish"
            assert payload["importance"] == 0.8  # Default
            assert payload["layer"] == "semantic"  # Default
            assert payload["type"] == "explicit"  # Always explicit
            assert payload["confidence"] == 0.95  # High confidence
            assert payload["persona_tags"] == []  # Default
            # Metadata includes source: llm_explicit
            assert payload["metadata"]["source"] == "llm_explicit"

    @pytest.mark.asyncio
    async def test_store_memory_with_all_general_fields(self):
        """Test memory storage with all general fields provided."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "memory_id": "mem_abc123",
            "message": "Memory stored successfully",
            "storage": {"chromadb": True, "episodic": False, "emotional": False, "procedural": False}
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="user123",
                content="User prefers conservative investments",
                importance=0.95,
                layer="long-term",
                persona_tags=["finance", "risk_tolerance"],
                metadata={"conversation_id": "conv_123", "trigger": "explicit_request"}
            )

            # Verify result
            assert result["status"] == "success"

            # Verify payload includes all provided values
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            assert payload["importance"] == 0.95
            assert payload["layer"] == "long-term"
            assert payload["type"] == "explicit"
            assert payload["confidence"] == 0.95
            assert payload["persona_tags"] == ["finance", "risk_tolerance"]
            # Metadata merges source: llm_explicit with user-provided metadata (AC #3)
            assert payload["metadata"]["source"] == "llm_explicit"
            assert payload["metadata"]["conversation_id"] == "conv_123"
            assert payload["metadata"]["trigger"] == "explicit_request"

    @pytest.mark.asyncio
    async def test_store_memory_metadata_merge(self):
        """Test that metadata correctly merges source: llm_explicit with user metadata."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "memory_id": "mem_test",
            "storage": {"chromadb": True}
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            # User provides their own source - should be overwritten
            await store_memory_tool_handler(
                user_id="user123",
                content="Test",
                metadata={"source": "custom", "extra": "data"}
            )

            payload = mock_client.post.call_args[1]["json"]
            # User's source should override default (user metadata merged on top)
            assert payload["metadata"]["source"] == "custom"
            assert payload["metadata"]["extra"] == "data"

    @pytest.mark.asyncio
    async def test_store_memory_persona_tags_limit(self):
        """Test that persona_tags is limited to max 10 items (AC #3)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "memory_id": "mem_test",
            "storage": {"chromadb": True}
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            # Provide more than 10 tags
            await store_memory_tool_handler(
                user_id="user123",
                content="Test",
                persona_tags=["tag1", "tag2", "tag3", "tag4", "tag5", "tag6",
                             "tag7", "tag8", "tag9", "tag10", "tag11", "tag12"]
            )

            payload = mock_client.post.call_args[1]["json"]
            # Should be limited to 10
            assert len(payload["persona_tags"]) == 10
            assert payload["persona_tags"] == ["tag1", "tag2", "tag3", "tag4", "tag5",
                                                "tag6", "tag7", "tag8", "tag9", "tag10"]

    @pytest.mark.asyncio
    async def test_store_memory_with_episodic_fields(self):
        """Test memory storage with episodic fields (event with time/place)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "memory_id": "mem_episodic_123",
            "message": "Memory stored successfully",
            "storage": {
                "chromadb": True,
                "episodic": True,
                "emotional": False,
                "procedural": False
            }
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="user123",
                content="User's mother passed away",
                event_timestamp="2024-03-15T10:30:00Z",
                location="San Francisco",
                participants=["user", "family"]
            )

            # Verify result shows episodic storage (AC #4)
            assert result["status"] == "success"
            assert result["storage"]["episodic"] is True

            # Verify episodic fields in payload (AC #3)
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            assert payload["event_timestamp"] == "2024-03-15T10:30:00Z"
            assert payload["location"] == "San Francisco"
            assert payload["participants"] == ["user", "family"]

    @pytest.mark.asyncio
    async def test_store_memory_with_emotional_fields(self):
        """Test memory storage with emotional context."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "memory_id": "mem_emotional_123",
            "storage": {
                "chromadb": True,
                "episodic": False,
                "emotional": True,
                "procedural": False
            }
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="user123",
                content="User just got promoted at work",
                emotional_state="excited",
                valence=0.9,
                arousal=0.8
            )

            # Verify result shows emotional storage (AC #4)
            assert result["status"] == "success"
            assert result["storage"]["emotional"] is True

            # Verify emotional fields in payload (AC #3)
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            assert payload["emotional_state"] == "excited"
            assert payload["valence"] == 0.9
            assert payload["arousal"] == 0.8

    @pytest.mark.asyncio
    async def test_store_memory_with_procedural_fields(self):
        """Test memory storage with procedural/skill fields."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "memory_id": "mem_procedural_123",
            "storage": {
                "chromadb": True,
                "episodic": False,
                "emotional": False,
                "procedural": True
            }
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="user123",
                content="User knows how to trade options",
                skill_name="options_trading",
                proficiency_level="intermediate"
            )

            # Verify result shows procedural storage (AC #4)
            assert result["status"] == "success"
            assert result["storage"]["procedural"] is True

            # Verify procedural fields in payload (AC #3)
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            assert payload["skill_name"] == "options_trading"
            assert payload["proficiency_level"] == "intermediate"

    @pytest.mark.asyncio
    async def test_store_memory_with_all_field_types(self):
        """Test memory storage with all optional field types combined."""
        mock_response = Mock()
        mock_response.status_code = 201  # Accept 201 as well
        mock_response.json.return_value = {
            "status": "success",
            "memory_id": "mem_combined_123",
            "message": "Memory stored successfully",
            "storage": {
                "chromadb": True,
                "episodic": True,
                "emotional": True,
                "procedural": True
            }
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="user123",
                content="User learned stock analysis after promotion",
                importance=0.9,
                layer="long-term",
                persona_tags=["career", "finance"],
                metadata={"trigger": "explicit_request"},
                # Episodic
                event_timestamp="2024-06-01T09:00:00Z",
                location="Office",
                participants=["user", "manager"],
                # Emotional
                emotional_state="proud",
                valence=0.85,
                arousal=0.7,
                # Procedural
                skill_name="stock_analysis",
                proficiency_level="beginner"
            )

            # Verify all storage types (AC #4)
            assert result["status"] == "success"
            assert result["storage"]["chromadb"] is True
            assert result["storage"]["episodic"] is True
            assert result["storage"]["emotional"] is True
            assert result["storage"]["procedural"] is True

            # Verify all fields present in payload
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]

            # Required
            assert payload["user_id"] == "user123"
            assert payload["content"] == "User learned stock analysis after promotion"

            # General (AC #3)
            assert payload["importance"] == 0.9
            assert payload["layer"] == "long-term"
            assert payload["type"] == "explicit"
            assert payload["confidence"] == 0.95
            assert payload["persona_tags"] == ["career", "finance"]
            assert payload["metadata"]["source"] == "llm_explicit"
            assert payload["metadata"]["trigger"] == "explicit_request"

            # Episodic
            assert payload["event_timestamp"] == "2024-06-01T09:00:00Z"
            assert payload["location"] == "Office"
            assert payload["participants"] == ["user", "manager"]

            # Emotional
            assert payload["emotional_state"] == "proud"
            assert payload["valence"] == 0.85
            assert payload["arousal"] == 0.7

            # Procedural
            assert payload["skill_name"] == "stock_analysis"
            assert payload["proficiency_level"] == "beginner"

    @pytest.mark.asyncio
    async def test_store_memory_without_optional_fields(self):
        """Test memory storage without optional fields."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "memory_id": "mem_test",
            "storage": {"chromadb": True}
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="user123",
                content="Simple memory content"
            )

            # Verify result
            assert result["status"] == "success"

            # Verify optional fields are NOT in payload when not provided
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]

            # These should NOT be present (only added when explicitly provided)
            assert "event_timestamp" not in payload
            assert "location" not in payload
            assert "participants" not in payload
            assert "emotional_state" not in payload
            assert "valence" not in payload
            assert "arousal" not in payload
            assert "skill_name" not in payload
            assert "proficiency_level" not in payload

            # But metadata should always be present with source
            assert payload["metadata"]["source"] == "llm_explicit"

    @pytest.mark.asyncio
    async def test_store_memory_timeout_10s(self):
        """Test that timeout is set to 10s (AC #2)."""
        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client_class.return_value.__aenter__ = AsyncMock()
            mock_client_class.return_value.__aexit__ = AsyncMock()

            # Verify timeout parameter
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "status": "success",
                "memory_id": "test",
                "storage": {}
            }

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await store_memory_tool_handler(
                user_id="user123",
                content="Test"
            )

            # Check that AsyncClient was called with timeout=10.0
            mock_client_class.assert_called_once_with(timeout=10.0)

    @pytest.mark.asyncio
    async def test_store_memory_timeout_error_message(self):
        """Test timeout error message includes timeout duration (AC #2)."""
        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.memory.asyncio.sleep', new_callable=AsyncMock):
                result = await store_memory_tool_handler(
                    user_id="user123",
                    content="Test memory"
                )

                assert result["status"] == "error"
                assert result["error_code"] == "TIMEOUT_ERROR"
                assert "10s timeout" in result["message"]

    @pytest.mark.asyncio
    async def test_store_memory_no_retry_on_validation_error(self):
        """Test no retry on VALIDATION_ERROR (AC #5)."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "status": "error",
            "message": "Content too long",
            "error_code": "VALIDATION_ERROR"
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="user123",
                content="Test memory"
            )

            assert result["status"] == "error"
            assert result["error_code"] == "VALIDATION_ERROR"
            # Should NOT retry - only 1 call
            assert mock_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_store_memory_no_retry_on_internal_error(self):
        """Test no retry on INTERNAL_ERROR (AC #5)."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {
            "status": "error",
            "message": "Internal server error",
            "error_code": "INTERNAL_ERROR"
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="user123",
                content="Test memory"
            )

            assert result["status"] == "error"
            assert result["error_code"] == "INTERNAL_ERROR"
            # Should NOT retry - only 1 call
            assert mock_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_store_memory_retry_on_embedding_error(self):
        """Test retry with backoff on EMBEDDING_ERROR (AC #5)."""
        mock_response_fail = Mock()
        mock_response_fail.status_code = 500
        mock_response_fail.json.return_value = {
            "status": "error",
            "message": "Embedding service unavailable",
            "error_code": "EMBEDDING_ERROR"
        }

        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {
            "status": "success",
            "memory_id": "mem_test",
            "storage": {"chromadb": True}
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(side_effect=[
                mock_response_fail,
                mock_response_fail,
                mock_response_success
            ])
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.memory.asyncio.sleep', new_callable=AsyncMock):
                result = await store_memory_tool_handler(
                    user_id="user123",
                    content="Test memory"
                )

                assert result["status"] == "success"
                # Should retry - 3 calls
                assert mock_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_store_memory_retry_on_storage_error(self):
        """Test retry with backoff on STORAGE_ERROR (AC #5)."""
        mock_response_fail = Mock()
        mock_response_fail.status_code = 503
        mock_response_fail.json.return_value = {
            "status": "error",
            "message": "Storage service unavailable",
            "error_code": "STORAGE_ERROR"
        }

        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {
            "status": "success",
            "memory_id": "mem_test",
            "storage": {"chromadb": True}
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(side_effect=[
                mock_response_fail,
                mock_response_success
            ])
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.memory.asyncio.sleep', new_callable=AsyncMock):
                result = await store_memory_tool_handler(
                    user_id="user123",
                    content="Test memory"
                )

                assert result["status"] == "success"
                # Should retry - 2 calls
                assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_store_memory_retries_on_server_error(self):
        """Test retry logic on server error (5xx) without error code."""
        mock_response_fail = Mock()
        mock_response_fail.status_code = 503
        mock_response_fail.json.return_value = {"message": "Service unavailable"}
        mock_response_fail.text = "Service unavailable"

        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {
            "status": "success",
            "memory_id": "mem_test",
            "storage": {"chromadb": True}
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(side_effect=[
                mock_response_fail,
                mock_response_fail,
                mock_response_success
            ])
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.memory.asyncio.sleep', new_callable=AsyncMock):
                result = await store_memory_tool_handler(
                    user_id="user123",
                    content="Test memory"
                )

                assert result["status"] == "success"
                assert mock_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_store_memory_no_retry_on_client_error(self):
        """Test no retry on client error (4xx) without retryable error code."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"message": "Invalid request"}
        mock_response.text = "Invalid request"

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="user123",
                content="Test memory"
            )

            assert result["status"] == "error"
            assert mock_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_store_memory_retries_on_network_error(self):
        """Test retry logic on network errors."""
        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {
            "status": "success",
            "memory_id": "mem_test",
            "storage": {"chromadb": True}
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(side_effect=[
                httpx.ConnectError("Connection refused"),
                httpx.NetworkError("Network error"),
                mock_response_success
            ])
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.memory.asyncio.sleep', new_callable=AsyncMock):
                result = await store_memory_tool_handler(
                    user_id="user123",
                    content="Test memory"
                )

                assert result["status"] == "success"
                assert mock_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_store_memory_fails_after_max_retries(self):
        """Test failure after max retries exceeded."""
        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.memory.asyncio.sleep', new_callable=AsyncMock):
                result = await store_memory_tool_handler(
                    user_id="user123",
                    content="Test memory"
                )

                assert result["status"] == "error"
                assert result["error_code"] == "NETWORK_ERROR"
                assert "3 attempts" in result["message"]
                assert mock_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_store_memory_handles_unexpected_errors(self):
        """Test handling of unexpected errors."""
        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(side_effect=ValueError("Unexpected error"))
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="user123",
                content="Test memory"
            )

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
            "storage": {"chromadb": True}
        }

        with patch('mcp_server.tools.memory.get_config') as mock_config:
            mock_config.return_value = {"AGENTIC_MEMORIES_URL": "http://custom:9000"}

            with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client

                await store_memory_tool_handler(
                    user_id="user123",
                    content="Test memory"
                )

                call_args = mock_client.post.call_args
                # Should use custom URL with new endpoint
                assert call_args[0][0] == "http://custom:9000/v1/memories/direct"

    @pytest.mark.asyncio
    async def test_store_memory_accepts_201_response(self):
        """Test that 201 Created is also accepted as success."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "status": "success",
            "memory_id": "mem_created",
            "message": "Memory created",
            "storage": {"chromadb": True}
        }

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await store_memory_tool_handler(
                user_id="user123",
                content="Test memory"
            )

            assert result["status"] == "success"
            assert result["memory_id"] == "mem_created"

    @pytest.mark.asyncio
    async def test_store_memory_default_importance(self):
        """Test that importance defaults to 0.8."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "memory_id": "mem_test", "storage": {}}

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await store_memory_tool_handler(user_id="user123", content="Test")

            payload = mock_client.post.call_args[1]["json"]
            assert payload["importance"] == 0.8

    @pytest.mark.asyncio
    async def test_store_memory_default_layer(self):
        """Test that layer defaults to 'semantic'."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "memory_id": "mem_test", "storage": {}}

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await store_memory_tool_handler(user_id="user123", content="Test")

            payload = mock_client.post.call_args[1]["json"]
            assert payload["layer"] == "semantic"

    @pytest.mark.asyncio
    async def test_store_memory_fixed_type_and_confidence(self):
        """Test that type is always 'explicit' and confidence is always 0.95."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "memory_id": "mem_test", "storage": {}}

        with patch('mcp_server.tools.memory.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await store_memory_tool_handler(user_id="user123", content="Test")

            payload = mock_client.post.call_args[1]["json"]
            assert payload["type"] == "explicit"
            assert payload["confidence"] == 0.95


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

    def test_tool_description_includes_guidance(self):
        """Test tool description includes usage guidance for LLM.

        Story 22.3 rewrote the description around the permanent-vs-day-scoped
        decision tree. It now points at `update_daily_context` for
        day-scoped facts instead of blaming "background extraction".
        """
        desc = store_memory_tool["description"]
        # Should mention PERMANENT memory as the framing
        assert "PERMANENT" in desc
        # Should list good uses
        assert "Examples of good uses" in desc
        # Should list bad uses
        assert "Examples of bad uses" in desc
        # Should redirect day-scoped facts to update_daily_context
        assert "update_daily_context" in desc
        # The misleading "background extraction handles this" framing is gone
        assert "background extraction" not in desc

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
        """Test input schema required fields are user_id and content (not history)."""
        schema = store_memory_tool["inputSchema"]
        required = schema["required"]
        assert "user_id" in required
        assert "content" in required
        # Old field should NOT be required
        assert "history" not in required

    def test_content_field_replaces_history(self):
        """Test that content field exists and history is removed."""
        properties = store_memory_tool["inputSchema"]["properties"]
        assert "content" in properties
        assert "history" not in properties
        assert properties["content"]["type"] == "string"
        assert properties["content"]["maxLength"] == 5000

    def test_general_fields_exist(self):
        """Test general fields exist with correct types."""
        properties = store_memory_tool["inputSchema"]["properties"]

        # importance
        assert "importance" in properties
        assert properties["importance"]["type"] == "number"
        assert properties["importance"]["minimum"] == 0.0
        assert properties["importance"]["maximum"] == 1.0
        assert properties["importance"]["default"] == 0.8

        # layer
        assert "layer" in properties
        assert properties["layer"]["type"] == "string"
        assert "enum" in properties["layer"]
        assert set(properties["layer"]["enum"]) == {"short-term", "semantic", "long-term"}
        assert properties["layer"]["default"] == "semantic"

        # persona_tags
        assert "persona_tags" in properties
        assert properties["persona_tags"]["type"] == "array"
        assert properties["persona_tags"]["items"]["type"] == "string"
        assert properties["persona_tags"]["maxItems"] == 10
        assert properties["persona_tags"]["default"] == []

    def test_episodic_fields_exist(self):
        """Test episodic fields exist with correct types."""
        properties = store_memory_tool["inputSchema"]["properties"]

        # event_timestamp
        assert "event_timestamp" in properties
        assert properties["event_timestamp"]["type"] == "string"
        assert properties["event_timestamp"]["format"] == "date-time"

        # location
        assert "location" in properties
        assert properties["location"]["type"] == "string"

        # participants
        assert "participants" in properties
        assert properties["participants"]["type"] == "array"
        assert properties["participants"]["items"]["type"] == "string"

    def test_emotional_fields_exist(self):
        """Test emotional fields exist with correct types."""
        properties = store_memory_tool["inputSchema"]["properties"]

        # emotional_state
        assert "emotional_state" in properties
        assert properties["emotional_state"]["type"] == "string"

        # valence
        assert "valence" in properties
        assert properties["valence"]["type"] == "number"
        assert properties["valence"]["minimum"] == -1.0
        assert properties["valence"]["maximum"] == 1.0

        # arousal
        assert "arousal" in properties
        assert properties["arousal"]["type"] == "number"
        assert properties["arousal"]["minimum"] == 0.0
        assert properties["arousal"]["maximum"] == 1.0

    def test_procedural_fields_exist(self):
        """Test procedural fields exist with correct types."""
        properties = store_memory_tool["inputSchema"]["properties"]

        # skill_name
        assert "skill_name" in properties
        assert properties["skill_name"]["type"] == "string"

        # proficiency_level
        assert "proficiency_level" in properties
        assert properties["proficiency_level"]["type"] == "string"
        assert "enum" in properties["proficiency_level"]
        assert set(properties["proficiency_level"]["enum"]) == {"beginner", "intermediate", "advanced", "expert"}

    def test_metadata_field_updated(self):
        """Test metadata field has updated properties."""
        metadata = store_memory_tool["inputSchema"]["properties"]["metadata"]
        assert metadata["type"] == "object"
        assert "properties" in metadata
        # Check updated properties
        assert "source" in metadata["properties"]
        assert "conversation_id" in metadata["properties"]
        assert "trigger" in metadata["properties"]

    def test_all_optional_fields_not_in_required(self):
        """Test that all optional fields are not in required list."""
        schema = store_memory_tool["inputSchema"]
        required = set(schema["required"])
        optional_fields = {
            "importance", "layer", "persona_tags", "metadata",
            "event_timestamp", "location", "participants",
            "emotional_state", "valence", "arousal",
            "skill_name", "proficiency_level"
        }
        # None of the optional fields should be required
        assert required.isdisjoint(optional_fields)

    def test_schema_is_valid_json_schema(self):
        """Test that schema is valid JSON Schema."""
        schema = store_memory_tool["inputSchema"]
        # Basic JSON Schema validation
        assert schema["type"] == "object"
        assert isinstance(schema["properties"], dict)
        assert isinstance(schema["required"], list)
        # All required fields must exist in properties
        for req_field in schema["required"]:
            assert req_field in schema["properties"]
        # All property values must be dicts with "type" key
        for prop_name, prop_schema in schema["properties"].items():
            assert isinstance(prop_schema, dict)
            assert "type" in prop_schema

    def test_field_descriptions_exist(self):
        """Test all fields have descriptions."""
        properties = store_memory_tool["inputSchema"]["properties"]
        for prop_name, prop_schema in properties.items():
            assert "description" in prop_schema, f"Missing description for {prop_name}"
            assert len(prop_schema["description"]) > 0, f"Empty description for {prop_name}"
