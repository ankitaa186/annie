"""
Unit Tests for GeminiProvider

Tests configuration, streaming, error handling, and integration for Gemini 3 Pro provider.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from api.constants import MODEL_GEMINI_PRO
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
            "GEMINI_MODEL": "gemini-3.1-pro-preview",
            "GEMINI_MAX_OUTPUT_TOKENS": "8192",
            "GEMINI_TEMPERATURE": "1.0",
            "GEMINI_SAFETY_SETTING": "BLOCK_NONE",
            "GEMINI_CONTEXT_CACHE_TTL": "300"
        }

        provider = GeminiProvider()

        assert provider.api_key == "test-api-key"
        assert provider.model_name == MODEL_GEMINI_PRO
        assert provider.max_output_tokens == 8192  # Matches config value passed above
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

        assert provider.model_name == MODEL_GEMINI_PRO
        assert provider.max_output_tokens == 16384  # Code default when env var not set
        assert provider.temperature == 1.0

    @patch('api.providers.gemini_provider.get_config')
    @patch('api.providers.gemini_provider.genai.configure')
    @patch('api.providers.gemini_provider.genai.GenerativeModel')
    def test_get_provider_name(self, mock_model, mock_configure, mock_get_config):
        """Test get_provider_name returns correct provider name."""
        mock_get_config.return_value = {"GEMINI_API_KEY": "test-api-key"}

        provider = GeminiProvider()
        assert provider.get_provider_name() == MODEL_GEMINI_PRO


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
            provider=MODEL_GEMINI_PRO,
            prompt_tokens=100,
            completion_tokens=50,
            sources_used=0,
            cached_tokens=0
        )
        assert cost["total_cost_usd"] == 0.06
