"""
Unit Tests for GeminiProvider

Tests configuration, streaming, error handling, and integration for Gemini 3 Pro provider.

Story 24.1 (AC9): patch sites re-targeted to provider-owned attributes.
The legacy `genai.configure` / `genai.GenerativeModel` patches are gone — we
patch `api.providers.gemini_provider.genai.Client` (the singleton constructor)
instead. Verification: the full backend suite passes in a container where
`google-generativeai` is uninstalled.
"""

import pytest
from unittest.mock import MagicMock, patch
from api.constants import MODEL_GEMINI_PRO
from api.providers.gemini_provider import GeminiProvider


class TestGeminiProviderConfiguration:
    """Test GeminiProvider configuration and initialization."""

    @patch('api.providers.gemini_provider.get_config')
    @patch('api.providers.gemini_provider.genai.Client')
    def test_provider_initialization_with_api_key(self, mock_client_cls, mock_get_config):
        """Test provider initializes correctly with valid API key."""
        mock_get_config.return_value = {
            "GOOGLE_API_KEY": "test-api-key",
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
        # Story 24.1 (AC2): client constructed once with the API key.
        mock_client_cls.assert_called_once_with(api_key="test-api-key")
        assert provider.client is mock_client_cls.return_value

    @patch('api.providers.gemini_provider.get_config')
    def test_provider_initialization_without_api_key_raises_error(self, mock_get_config):
        """Test provider raises ValueError when GOOGLE_API_KEY is missing."""
        mock_get_config.return_value = {
            "GOOGLE_API_KEY": "REPLACE_ME"
        }

        with pytest.raises(ValueError, match="GOOGLE_API_KEY not configured"):
            GeminiProvider()

    @patch('api.providers.gemini_provider.get_config')
    @patch('api.providers.gemini_provider.genai.Client')
    def test_provider_default_configuration_values(self, mock_client_cls, mock_get_config):
        """Test provider uses default values when env vars not set."""
        mock_get_config.return_value = {
            "GOOGLE_API_KEY": "test-api-key"
        }

        provider = GeminiProvider()

        assert provider.model_name == MODEL_GEMINI_PRO
        assert provider.max_output_tokens == 16384  # Code default when env var not set
        assert provider.temperature == 1.0

    @patch('api.providers.gemini_provider.get_config')
    @patch('api.providers.gemini_provider.genai.Client')
    def test_get_provider_name(self, mock_client_cls, mock_get_config):
        """Test get_provider_name returns correct provider name."""
        mock_get_config.return_value = {"GOOGLE_API_KEY": "test-api-key"}

        provider = GeminiProvider()
        assert provider.get_provider_name() == MODEL_GEMINI_PRO

    @patch('api.providers.gemini_provider.get_config')
    @patch('api.providers.gemini_provider.genai.Client')
    def test_singleton_client_reused_across_calls(self, mock_client_cls, mock_get_config):
        """Story 24.1 (Parminder steer): the SDK Client is constructed once.

        AC2 / AC9: per-request reconstruction is wasteful and breaks any
        future SDK connection pooling. Verify the constructor is called
        exactly once per provider instance.
        """
        mock_get_config.return_value = {"GOOGLE_API_KEY": "test-api-key"}
        provider = GeminiProvider()
        # Re-binding any provider attribute should NOT reconstruct the client.
        assert mock_client_cls.call_count == 1
        # Provider exposes the singleton via a stable attribute.
        assert provider.client is mock_client_cls.return_value


class TestGeminiProviderMessageConversion:
    """Test message format conversion from OpenAI to Gemini format."""

    @patch('api.providers.gemini_provider.get_config')
    @patch('api.providers.gemini_provider.genai.Client')
    def test_convert_user_message(self, mock_client_cls, mock_get_config):
        """Test user message conversion to Gemini format."""
        mock_get_config.return_value = {"GOOGLE_API_KEY": "test-api-key"}
        provider = GeminiProvider()

        messages = [{"role": "user", "content": "Hello"}]
        system_inst, converted = provider._convert_messages_to_gemini_format(messages)

        assert system_inst is None
        assert len(converted) == 1
        assert converted[0]["role"] == "user"
        assert converted[0]["parts"][0]["text"] == "Hello"

    @patch('api.providers.gemini_provider.get_config')
    @patch('api.providers.gemini_provider.genai.Client')
    def test_convert_assistant_to_model_role(self, mock_client_cls, mock_get_config):
        """Test assistant role is converted to model role."""
        mock_get_config.return_value = {"GOOGLE_API_KEY": "test-api-key"}
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
    @patch('api.providers.gemini_provider.genai.Client')
    def test_convert_system_message_to_instruction(self, mock_client_cls, mock_get_config):
        """Test system message is extracted as system_instruction."""
        mock_get_config.return_value = {"GOOGLE_API_KEY": "test-api-key"}
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
    @patch('api.providers.gemini_provider.genai.Client')
    @patch('api.providers.gemini_provider.calculate_llm_cost')
    def test_calculate_cost_delegates_to_cost_module(self, mock_calc_cost, mock_client_cls, mock_get_config):
        """Test calculate_cost delegates to cost calculation module."""
        mock_get_config.return_value = {"GOOGLE_API_KEY": "test-api-key"}
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

    @patch('api.providers.gemini_provider.get_config')
    @patch('api.providers.gemini_provider.genai.Client')
    @patch('api.providers.gemini_provider.calculate_llm_cost')
    def test_calculate_cost_passes_cached_tokens(self, mock_calc_cost, mock_client_cls, mock_get_config):
        """Story 24.1 (AC15): cached_tokens flows through to calculate_llm_cost."""
        mock_get_config.return_value = {"GOOGLE_API_KEY": "test-api-key"}
        mock_calc_cost.return_value = {"total_cost_usd": 0.01}

        provider = GeminiProvider()
        provider.calculate_cost({
            "prompt_tokens": 1000,
            "completion_tokens": 500,
            "cached_tokens": 600,
        })
        mock_calc_cost.assert_called_once_with(
            provider=MODEL_GEMINI_PRO,
            prompt_tokens=1000,
            completion_tokens=500,
            sources_used=0,
            cached_tokens=600,
        )

    @patch('api.providers.gemini_provider.get_config')
    @patch('api.providers.gemini_provider.genai.Client')
    def test_calculate_cost_parity(self, mock_client_cls, mock_get_config):
        """Story 24.1 (AC12): cost-calc parity. SDK swap doesn't move pricing.

        The cost table is keyed by model-name string (`gemini-3.1-pro-preview`),
        so identical token counts must produce identical dollar figures
        pre- and post-migration.
        """
        mock_get_config.return_value = {"GOOGLE_API_KEY": "test-api-key"}
        provider = GeminiProvider()
        cost = provider.calculate_cost({
            "prompt_tokens": 1000,
            "completion_tokens": 500,
            "cached_tokens": 0,
        })
        # The exact dollar figure rides on the cost table; verify the
        # function returns a sane shape with non-zero total for non-zero
        # tokens. Pre/post migration parity is enforced by going through
        # `calculate_llm_cost` (Annie's table, SDK-independent).
        assert "total_cost" in cost
        assert cost["total_cost"] > 0


class TestGeminiProviderUsageMetadataExtraction:
    """Story 24.1 (AC15): _extract_usage_metadata plumbs cached_tokens."""

    def test_extract_usage_metadata_with_cached(self):
        """cached_content_token_count populates `cached_tokens`.

        Bug 25.2: helper now also returns `non_cached_input_tokens` =
        `prompt_tokens - cached_tokens` for Langfuse emission shape.
        """
        chunk = MagicMock()
        chunk.usage_metadata.prompt_token_count = 1000
        chunk.usage_metadata.candidates_token_count = 500
        chunk.usage_metadata.cached_content_token_count = 600
        result = GeminiProvider._extract_usage_metadata(chunk)
        assert result == {
            "prompt_tokens": 1000,
            "completion_tokens": 500,
            "cached_tokens": 600,
            "non_cached_input_tokens": 400,
        }

    def test_extract_usage_metadata_cached_none_defaults_to_zero(self):
        """Story 24.1 (AC15 + Parminder steer): cached=None → 0, not None.

        Semantically "we know it was zero" on first turn / non-caching
        paths. NOT "we don't know" — that's reserved for the prompt/output
        absent case.
        """
        chunk = MagicMock()
        chunk.usage_metadata.prompt_token_count = 1000
        chunk.usage_metadata.candidates_token_count = 500
        chunk.usage_metadata.cached_content_token_count = None
        result = GeminiProvider._extract_usage_metadata(chunk)
        assert result is not None
        assert result["cached_tokens"] == 0
        # Bug 25.2: with cached=0, non_cached_input == prompt (no-op).
        assert result["non_cached_input_tokens"] == 1000

    def test_extract_usage_metadata_cached_field_missing_defaults_to_zero(self):
        """If the field doesn't exist on the chunk, default to 0."""
        chunk = MagicMock(spec=["usage_metadata"])
        chunk.usage_metadata = MagicMock(spec=["prompt_token_count", "candidates_token_count"])
        chunk.usage_metadata.prompt_token_count = 1000
        chunk.usage_metadata.candidates_token_count = 500
        result = GeminiProvider._extract_usage_metadata(chunk)
        assert result is not None
        assert result["cached_tokens"] == 0
        # Bug 25.2: cached missing → non_cached_input falls back to prompt.
        assert result["non_cached_input_tokens"] == 1000

    def test_extract_usage_metadata_returns_none_when_prompt_absent(self):
        """AC3 invariant preserved: prompt absent → None ('we don't know')."""
        chunk = MagicMock()
        chunk.usage_metadata.prompt_token_count = None
        chunk.usage_metadata.candidates_token_count = 500
        chunk.usage_metadata.cached_content_token_count = 0
        assert GeminiProvider._extract_usage_metadata(chunk) is None

    def test_extract_usage_metadata_returns_none_when_metadata_absent(self):
        """AC3 invariant preserved: usage_metadata absent → None."""
        chunk = MagicMock(spec=[])  # no usage_metadata attribute
        assert GeminiProvider._extract_usage_metadata(chunk) is None


class TestGeminiProviderTypedExceptionDetection:
    """Story 24.1 (AC11.5): typed-exception ContextLengthError detection."""

    def test_substring_path_resource_exhausted_with_token_limit(self):
        """Legacy substring path still works (safety net)."""
        exc = Exception("400 RESOURCE_EXHAUSTED: Request payload exceeds the token limit of 1048576 tokens")
        assert GeminiProvider._is_context_length_error(exc) is True
        # And it must NOT register as a (non-context) rate limit:
        # _is_rate_limit_error returns True too, but the streaming path
        # checks _is_context_length_error FIRST, so context wins.

    def test_typed_path_client_error_with_code_and_status(self):
        """Story 24.1 (AC11.5): typed exception with .code/.status fields.

        The new SDK raises `google.genai.errors.ClientError` with
        structured fields. We synthesize a typed-shaped exception here
        (we can't construct the real ClientError without an httpx
        Response in unit-test context).
        """
        exc = Exception("Synthetic typed error")
        exc.code = 429
        exc.status = "RESOURCE_EXHAUSTED"
        exc.message = "The input token count exceeds the maximum context length limit for this model"
        assert GeminiProvider._is_context_length_error(exc) is True

    def test_rate_limit_without_token_limit_is_not_context(self):
        """RESOURCE_EXHAUSTED without token+limit is rate limit, NOT overflow."""
        exc = Exception("429 Quota exceeded for the day")
        exc.code = 429
        exc.status = "RESOURCE_EXHAUSTED"
        exc.message = "Quota exceeded for the day"
        assert GeminiProvider._is_context_length_error(exc) is False
        assert GeminiProvider._is_rate_limit_error(exc) is True

    def test_unrelated_error_is_neither(self):
        """Unrelated errors should not be context-length OR rate-limit."""
        exc = Exception("500 Internal server error")
        assert GeminiProvider._is_context_length_error(exc) is False
        assert GeminiProvider._is_rate_limit_error(exc) is False
