"""
Unit Tests for GeminiProvider

Tests configuration, streaming, error handling, and integration for Gemini 3 Pro provider.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from api.providers.gemini_provider import GeminiProvider, ProviderError, RateLimitError


class TestGeminiProviderConfiguration:
    """Test GeminiProvider configuration and initialization."""

    @patch('api.providers.gemini_provider.get_config')
    @patch('api.providers.gemini_provider.genai.configure')
    @patch('api.providers.gemini_provider.genai.GenerativeModel')
    def test_provider_initialization_with_api_key(self, mock_model, mock_configure, mock_get_config):
        """Test provider initializes correctly with valid API key."""
        mock_get_config.return_value = {
            "GEMINI_API_KEY": "test-api-key",
            "GEMINI_MODEL": "gemini-3-pro-preview",
            "GEMINI_MAX_OUTPUT_TOKENS": "8192",
            "GEMINI_TEMPERATURE": "1.0",
            "GEMINI_SAFETY_SETTING": "BLOCK_NONE",
            "GEMINI_CONTEXT_CACHE_TTL": "300"
        }

        provider = GeminiProvider()

        assert provider.api_key == "test-api-key"
        assert provider.model_name == "gemini-3-pro-preview"
        assert provider.max_output_tokens == 8192
        assert provider.temperature == 1.0
        mock_configure.assert_called_once_with(api_key="test-api-key")

    @patch('api.providers.gemini_provider.get_config')
    def test_provider_initialization_without_api_key_raises_error(self, mock_get_config):
        """Test provider raises ValueError when GEMINI_API_KEY is missing."""
        mock_get_config.return_value = {
            "GEMINI_API_KEY": "REPLACE_ME"
        }

        with pytest.raises(ValueError, match="GEMINI_API_KEY not configured"):
            GeminiProvider()

    @patch('api.providers.gemini_provider.get_config')
    @patch('api.providers.gemini_provider.genai.configure')
    @patch('api.providers.gemini_provider.genai.GenerativeModel')
    def test_provider_default_configuration_values(self, mock_model, mock_configure, mock_get_config):
        """Test provider uses default values when env vars not set."""
        mock_get_config.return_value = {
            "GEMINI_API_KEY": "test-api-key"
        }

        provider = GeminiProvider()

        assert provider.model_name == "gemini-3-pro-preview"
        assert provider.max_output_tokens == 8192
        assert provider.temperature == 1.0

    @patch('api.providers.gemini_provider.get_config')
    @patch('api.providers.gemini_provider.genai.configure')
    @patch('api.providers.gemini_provider.genai.GenerativeModel')
    def test_get_provider_name(self, mock_model, mock_configure, mock_get_config):
        """Test get_provider_name returns correct provider name."""
        mock_get_config.return_value = {"GEMINI_API_KEY": "test-api-key"}

        provider = GeminiProvider()
        assert provider.get_provider_name() == "gemini-3-pro-preview"


class TestGeminiProviderMessageConversion:
    """Test message format conversion from OpenAI to Gemini format."""

    @patch('api.providers.gemini_provider.get_config')
    @patch('api.providers.gemini_provider.genai.configure')
    @patch('api.providers.gemini_provider.genai.GenerativeModel')
    def test_convert_user_message(self, mock_model, mock_configure, mock_get_config):
        """Test user message conversion to Gemini format."""
        mock_get_config.return_value = {"GEMINI_API_KEY": "test-api-key"}
        provider = GeminiProvider()

        messages = [{"role": "user", "content": "Hello"}]
        system_inst, converted = provider._convert_messages_to_gemini_format(messages)

        assert system_inst is None
        assert len(converted) == 1
        assert converted[0]["role"] == "user"
        assert converted[0]["parts"][0]["text"] == "Hello"

    @patch('api.providers.gemini_provider.get_config')
    @patch('api.providers.gemini_provider.genai.configure')
    @patch('api.providers.gemini_provider.genai.GenerativeModel')
    def test_convert_assistant_to_model_role(self, mock_model, mock_configure, mock_get_config):
        """Test assistant role is converted to model role."""
        mock_get_config.return_value = {"GEMINI_API_KEY": "test-api-key"}
        provider = GeminiProvider()

        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"}
        ]
        system_inst, converted = provider._convert_messages_to_gemini_format(messages)

        assert len(converted) == 2
        assert converted[0]["role"] == "user"
        assert converted[1]["role"] == "model"  # assistant → model

    @patch('api.providers.gemini_provider.get_config')
    @patch('api.providers.gemini_provider.genai.configure')
    @patch('api.providers.gemini_provider.genai.GenerativeModel')
    def test_convert_system_message_to_instruction(self, mock_model, mock_configure, mock_get_config):
        """Test system message is extracted as system_instruction."""
        mock_get_config.return_value = {"GEMINI_API_KEY": "test-api-key"}
        provider = GeminiProvider()

        messages = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "Hello"}
        ]
        system_inst, converted = provider._convert_messages_to_gemini_format(messages)

        assert system_inst == "You are a helpful assistant"
        assert len(converted) == 1  # system message not in converted list


class TestGeminiProviderStreaming:
    """Test Gemini streaming functionality."""

    @pytest.mark.asyncio
    @patch('api.providers.gemini_provider.get_config')
    @patch('api.providers.gemini_provider.genai.configure')
    @patch('api.providers.gemini_provider.genai.GenerativeModel')
    @patch('api.providers.gemini_provider.get_current_trace')
    async def test_basic_streaming_response(self, mock_trace, mock_model_class, mock_configure, mock_get_config):
        """Test basic streaming response from Gemini."""
        mock_get_config.return_value = {"GEMINI_API_KEY": "test-api-key"}

        # Mock streaming response
        mock_chunk1 = Mock()
        mock_chunk1.candidates = [Mock()]
        mock_chunk1.candidates[0].content = Mock()
        mock_chunk1.candidates[0].content.parts = [Mock(text="Hello")]
        mock_chunk1.candidates[0].finish_reason = None
        mock_chunk1.prompt_feedback = None

        mock_chunk2 = Mock()
        mock_chunk2.candidates = [Mock()]
        mock_chunk2.candidates[0].content = Mock()
        mock_chunk2.candidates[0].content.parts = [Mock(text=" world")]
        mock_chunk2.candidates[0].finish_reason = "STOP"
        mock_chunk2.prompt_feedback = None

        mock_model_instance = Mock()
        mock_model_instance.generate_content = Mock(return_value=[mock_chunk1, mock_chunk2])
        mock_model_instance.count_tokens = Mock(return_value=Mock(total_tokens=10))
        mock_model_class.return_value = mock_model_instance

        provider = GeminiProvider()
        messages = [{"role": "user", "content": "Hi"}]

        tokens = []
        done_event = None
        async for event in provider.stream_chat_completion(messages):
            if event["type"] == "token":
                tokens.append(event["content"])
            elif event["type"] == "done":
                done_event = event

        assert tokens == ["Hello", " world"]
        assert done_event is not None
        assert "tokens_used" in done_event

    @pytest.mark.asyncio
    @patch('api.providers.gemini_provider.get_config')
    @patch('api.providers.gemini_provider.genai.configure')
    @patch('api.providers.gemini_provider.genai.GenerativeModel')
    @patch('api.providers.gemini_provider.get_current_trace')
    async def test_safety_filter_blocked_response(self, mock_trace, mock_model_class, mock_configure, mock_get_config):
        """Test safety filter block is handled gracefully."""
        mock_get_config.return_value = {"GEMINI_API_KEY": "test-api-key"}

        # Mock safety-blocked response
        mock_chunk = Mock()
        mock_chunk.candidates = [Mock()]
        mock_chunk.candidates[0].finish_reason = "SAFETY"
        mock_chunk.candidates[0].content = Mock()
        mock_chunk.candidates[0].content.parts = []
        mock_chunk.candidates[0].safety_ratings = []
        mock_chunk.prompt_feedback = None

        mock_model_instance = Mock()
        mock_model_instance.generate_content = Mock(return_value=[mock_chunk])
        mock_model_class.return_value = mock_model_instance

        provider = GeminiProvider()
        messages = [{"role": "user", "content": "Blocked content"}]

        events = []
        async for event in provider.stream_chat_completion(messages):
            events.append(event)

        # Should yield error event
        assert len(events) > 0
        assert events[0]["type"] == "error"
        assert "content policy" in events[0]["message"].lower()


class TestGeminiProviderErrorHandling:
    """Test error handling for quota, rate limits, and network errors."""

    @pytest.mark.asyncio
    @patch('api.providers.gemini_provider.get_config')
    @patch('api.providers.gemini_provider.genai.configure')
    @patch('api.providers.gemini_provider.genai.GenerativeModel')
    async def test_quota_error_raises_rate_limit_error(self, mock_model_class, mock_configure, mock_get_config):
        """Test quota exceeded raises RateLimitError."""
        mock_get_config.return_value = {"GEMINI_API_KEY": "test-api-key"}

        mock_model_instance = Mock()
        mock_model_instance.generate_content = Mock(side_effect=Exception("quota exceeded"))
        mock_model_class.return_value = mock_model_instance

        provider = GeminiProvider()
        messages = [{"role": "user", "content": "Test"}]

        with pytest.raises(RateLimitError):
            async for _ in provider.stream_chat_completion(messages):
                pass

    @pytest.mark.asyncio
    @patch('api.providers.gemini_provider.get_config')
    @patch('api.providers.gemini_provider.genai.configure')
    @patch('api.providers.gemini_provider.genai.GenerativeModel')
    async def test_resource_exhausted_raises_rate_limit_error(self, mock_model_class, mock_configure, mock_get_config):
        """Test resource exhausted raises RateLimitError."""
        mock_get_config.return_value = {"GEMINI_API_KEY": "test-api-key"}

        mock_model_instance = Mock()
        mock_model_instance.generate_content = Mock(side_effect=Exception("Resource exhausted"))
        mock_model_class.return_value = mock_model_instance

        provider = GeminiProvider()
        messages = [{"role": "user", "content": "Test"}]

        with pytest.raises(RateLimitError):
            async for _ in provider.stream_chat_completion(messages):
                pass

    @pytest.mark.asyncio
    @patch('api.providers.gemini_provider.get_config')
    @patch('api.providers.gemini_provider.genai.configure')
    @patch('api.providers.gemini_provider.genai.GenerativeModel')
    async def test_generic_error_raises_provider_error(self, mock_model_class, mock_configure, mock_get_config):
        """Test generic errors raise ProviderError."""
        mock_get_config.return_value = {"GEMINI_API_KEY": "test-api-key"}

        mock_model_instance = Mock()
        mock_model_instance.generate_content = Mock(side_effect=Exception("Network error"))
        mock_model_class.return_value = mock_model_instance

        provider = GeminiProvider()
        messages = [{"role": "user", "content": "Test"}]

        with pytest.raises(ProviderError):
            async for _ in provider.stream_chat_completion(messages):
                pass


class TestGeminiProviderCostCalculation:
    """Test cost calculation for Gemini 3 Pro."""

    @patch('api.providers.gemini_provider.get_config')
    @patch('api.providers.gemini_provider.genai.configure')
    @patch('api.providers.gemini_provider.genai.GenerativeModel')
    @patch('api.providers.gemini_provider.calculate_llm_cost')
    def test_calculate_cost_delegates_to_cost_module(self, mock_calc_cost, mock_model, mock_configure, mock_get_config):
        """Test calculate_cost delegates to cost calculation module."""
        mock_get_config.return_value = {"GEMINI_API_KEY": "test-api-key"}
        mock_calc_cost.return_value = {
            "input_cost_usd": 0.01,
            "output_cost_usd": 0.05,
            "total_cost_usd": 0.06
        }

        provider = GeminiProvider()
        usage = {"prompt_tokens": 100, "completion_tokens": 50}
        cost = provider.calculate_cost(usage)

        mock_calc_cost.assert_called_once_with(
            provider="gemini-3-pro-preview",
            prompt_tokens=100,
            completion_tokens=50,
            sources_used=0,
            cached_tokens=0
        )
        assert cost["total_cost_usd"] == 0.06
