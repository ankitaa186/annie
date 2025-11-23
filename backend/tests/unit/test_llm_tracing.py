"""
Unit tests for LLM generation tracing in llm_client.

Tests AC #3: LLM generation tracking with prompts, completions, tokens, and costs
"""
import pytest
from unittest.mock import patch, Mock, MagicMock, AsyncMock
import json


class TestLLMGenerationTracing:
    """Test AC #3: LLM generation tracking."""

    @pytest.mark.asyncio
    @patch("api.llm_client.get_current_trace")
    @patch("api.llm_client.calculate_llm_cost")
    async def test_generation_tracked_for_non_streaming_call(self, mock_calculate_cost, mock_get_trace):
        """Test that Langfuse generation is created for non-streaming LLM calls."""
        # Mock trace
        mock_trace = Mock()
        mock_trace.generation = Mock()
        mock_get_trace.return_value = mock_trace

        # Mock cost calculation
        mock_calculate_cost.return_value = {
            "input_cost": 0.03,
            "output_cost": 0.06,
            "total_cost": 0.09
        }

        # Mock HTTP response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "This is a test response"
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150
            }
        })

        # Create LLM client and mock HTTP client
        from api.llm_client import LLMClient

        with patch("httpx.AsyncClient") as mock_http_client:
            mock_client_instance = MagicMock()
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            mock_http_client.return_value = mock_client_instance

            client = LLMClient()
            client.client = mock_client_instance
            # Mock provider availability to allow chatgpt-5 calls
            client.providers_available["chatgpt-5"] = True
            client.chatgpt_api_key = "test_key"

            # Call provider
            await client._call_provider("chatgpt-5", [{"role": "user", "content": "Test"}])

            # Verify generation was tracked
            mock_trace.generation.assert_called_once()
            call_kwargs = mock_trace.generation.call_args[1]

            # Verify required fields
            assert "name" in call_kwargs
            assert "llm_call_chatgpt-5" in call_kwargs["name"]
            assert "input" in call_kwargs
            assert "output" in call_kwargs
            assert "model" in call_kwargs
            assert "usage" in call_kwargs
            assert call_kwargs["usage"]["input"] == 100
            assert call_kwargs["usage"]["output"] == 50

    @pytest.mark.asyncio
    @patch("api.llm_client.get_current_trace")
    async def test_prompt_truncated_to_1000_chars(self, mock_get_trace):
        """Test that prompts are truncated to 1000 characters as per Epic requirement."""
        # Mock trace
        mock_trace = Mock()
        mock_trace.generation = Mock()
        mock_get_trace.return_value = mock_trace

        # Create long message (> 1000 chars)
        long_message = "a" * 1500

        # Mock HTTP response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={
            "choices": [{"message": {"content": "Short response"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}
        })

        from api.llm_client import LLMClient

        with patch("httpx.AsyncClient") as mock_http_client:
            mock_client_instance = MagicMock()
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            mock_http_client.return_value = mock_client_instance

            client = LLMClient()
            client.client = mock_client_instance
            # Mock provider availability to allow chatgpt-5 calls
            client.providers_available["chatgpt-5"] = True
            client.chatgpt_api_key = "test_key"

            await client._call_provider("chatgpt-5", [{"role": "user", "content": long_message}])

            # Verify truncation
            call_kwargs = mock_trace.generation.call_args[1]
            truncated_input = call_kwargs["input"]

            # Should be truncated (1000 chars + "..." + truncation message)
            assert len(truncated_input) < len(json.dumps([{"role": "user", "content": long_message}]))
            assert "truncated from" in truncated_input

    @pytest.mark.asyncio
    @patch("api.llm_client.get_current_trace")
    @patch("api.llm_client.calculate_llm_cost")
    async def test_cost_included_in_generation(self, mock_calculate_cost, mock_get_trace):
        """Test that cost calculation is included in generation metadata."""
        mock_trace = Mock()
        mock_trace.generation = Mock()
        mock_get_trace.return_value = mock_trace

        mock_calculate_cost.return_value = {
            "input_cost": 0.015,
            "output_cost": 0.030,
            "total_cost": 0.045
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={
            "choices": [{"message": {"content": "Response"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 500, "completion_tokens": 500, "total_tokens": 1000}
        })

        from api.llm_client import LLMClient

        with patch("httpx.AsyncClient") as mock_http_client:
            mock_client_instance = MagicMock()
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            mock_http_client.return_value = mock_client_instance

            client = LLMClient()
            client.client = mock_client_instance
            # Mock provider availability to allow chatgpt-5 calls
            client.providers_available["chatgpt-5"] = True
            client.chatgpt_api_key = "test_key"

            await client._call_provider("chatgpt-5", [{"role": "user", "content": "Test"}])

            # Verify cost in generation
            call_kwargs = mock_trace.generation.call_args[1]
            assert "usage_details" in call_kwargs
            assert call_kwargs["usage_details"]["input_cost"] == 0.015
            assert call_kwargs["usage_details"]["output_cost"] == 0.030
            assert call_kwargs["usage_details"]["total_cost"] == 0.045

    @pytest.mark.asyncio
    @patch("api.llm_client.get_current_trace")
    async def test_tracing_fails_gracefully(self, mock_get_trace):
        """Test AC #6: Tracing failure doesn't block LLM call (fire-and-forget)."""
        # Mock trace that raises exception
        mock_trace = Mock()
        mock_trace.generation = Mock(side_effect=Exception("Langfuse connection failed"))
        mock_get_trace.return_value = mock_trace

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={
            "choices": [{"message": {"content": "Response"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        })

        from api.llm_client import LLMClient

        with patch("httpx.AsyncClient") as mock_http_client:
            mock_client_instance = MagicMock()
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            mock_http_client.return_value = mock_client_instance

            client = LLMClient()
            client.client = mock_client_instance
            # Mock provider availability to allow chatgpt-5 calls
            client.providers_available["chatgpt-5"] = True
            client.chatgpt_api_key = "test_key"

            # Call should succeed despite tracing failure
            result = await client._call_provider("chatgpt-5", [{"role": "user", "content": "Test"}])

            # Verify call succeeded
            assert result is not None
            assert "choices" in result

    @pytest.mark.asyncio
    @patch("api.llm_client.get_current_trace")
    async def test_provider_name_recorded_in_metadata(self, mock_get_trace):
        """Test that provider name is recorded in generation metadata."""
        mock_trace = Mock()
        mock_trace.generation = Mock()
        mock_get_trace.return_value = mock_trace

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={
            "choices": [{"message": {"content": "Response"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        })

        from api.llm_client import LLMClient

        with patch("httpx.AsyncClient") as mock_http_client:
            mock_client_instance = MagicMock()
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            mock_http_client.return_value = mock_client_instance

            client = LLMClient()
            client.client = mock_client_instance

            await client._call_provider("grok-4", [{"role": "user", "content": "Test"}])

            # Verify provider in metadata
            call_kwargs = mock_trace.generation.call_args[1]
            assert "metadata" in call_kwargs
            assert call_kwargs["metadata"]["provider"] == "grok-4"
