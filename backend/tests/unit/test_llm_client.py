"""
Unit tests for LLM Client

Tests cover:
- AC #1: Grok-4 authentication and API calls
- AC #2: Provider selection logic
- AC #3: Automatic failover within 2 seconds
- AC #4: User-friendly error messages when both providers fail
- AC #5: Structured error logging
- AC #6: Rate limiting and retry-after handling
- AC #7: Configuration via environment variables
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
import httpx
from api.llm_client import (
    LLMClient,
    LLMClientError,
    ProviderError,
    RateLimitError
)


@pytest.fixture
def mock_config_grok():
    """Mock configuration with Grok-4 as primary provider."""
    return {
        "LLM_PROVIDER": "grok-4",
        "GROK_API_KEY": "test-grok-key-12345",
        "CHATGPT_API_KEY": "test-chatgpt-key-12345"
    }


@pytest.fixture
def mock_config_chatgpt():
    """Mock configuration with ChatGPT-5 as primary provider."""
    return {
        "LLM_PROVIDER": "chatgpt-5",
        "GROK_API_KEY": "test-grok-key-12345",
        "CHATGPT_API_KEY": "test-chatgpt-key-12345"
    }


@pytest.fixture
def mock_config_grok_only():
    """Mock configuration with only Grok-4 configured."""
    return {
        "LLM_PROVIDER": "grok-4",
        "GROK_API_KEY": "test-grok-key-12345",
        "CHATGPT_API_KEY": None
    }


class TestLLMClientInitialization:
    """Test LLM client initialization and configuration (AC #1, #2, #7)."""

    @patch('api.llm_client.get_config')
    def test_init_with_grok_primary(self, mock_get_config, mock_config_grok):
        """Test initialization with Grok-4 as primary provider."""
        mock_get_config.return_value = mock_config_grok

        client = LLMClient()

        assert client.primary_provider == "grok-4"
        assert client.grok_api_key == "test-grok-key-12345"
        assert client.chatgpt_api_key == "test-chatgpt-key-12345"
        assert client.providers_available["grok-4"] is True
        assert client.providers_available["chatgpt-5"] is True

    @patch('api.llm_client.get_config')
    def test_init_with_chatgpt_primary(self, mock_get_config, mock_config_chatgpt):
        """Test initialization with ChatGPT-5 as primary provider."""
        mock_get_config.return_value = mock_config_chatgpt

        client = LLMClient()

        assert client.primary_provider == "chatgpt-5"
        assert client.providers_available["grok-4"] is True
        assert client.providers_available["chatgpt-5"] is True

    @patch('api.llm_client.get_config')
    def test_init_with_missing_fallback(self, mock_get_config, mock_config_grok_only):
        """Test initialization with only primary provider configured."""
        mock_get_config.return_value = mock_config_grok_only

        client = LLMClient()

        assert client.providers_available["grok-4"] is True
        assert client.providers_available["chatgpt-5"] is False

    @patch('api.llm_client.get_config')
    def test_init_with_invalid_provider(self, mock_get_config):
        """Test initialization with invalid provider defaults to grok-4."""
        mock_get_config.return_value = {
            "LLM_PROVIDER": "invalid-provider",
            "GROK_API_KEY": "test-key"
        }

        client = LLMClient()

        # Should default to grok-4
        assert client.primary_provider == "grok-4"


class TestProviderConfiguration:
    """Test provider configuration methods (AC #2, #7)."""

    @patch('api.llm_client.get_config')
    def test_get_provider_config_grok(self, mock_get_config, mock_config_grok):
        """Test getting Grok-4 provider configuration."""
        mock_get_config.return_value = mock_config_grok
        client = LLMClient()

        config = client._get_provider_config("grok-4")

        assert config["base_url"] == "https://api.x.ai/v1"
        assert config["api_key"] == "test-grok-key-12345"

    @patch('api.llm_client.get_config')
    def test_get_provider_config_chatgpt(self, mock_get_config, mock_config_grok):
        """Test getting ChatGPT-5 provider configuration."""
        mock_get_config.return_value = mock_config_grok
        client = LLMClient()

        config = client._get_provider_config("chatgpt-5")

        assert config["base_url"] == "https://api.openai.com/v1"
        assert config["api_key"] == "test-chatgpt-key-12345"

    @patch('api.llm_client.get_config')
    def test_get_provider_config_unconfigured(self, mock_get_config, mock_config_grok_only):
        """Test getting config for unconfigured provider raises error."""
        mock_get_config.return_value = mock_config_grok_only
        client = LLMClient()

        with pytest.raises(ProviderError) as exc_info:
            client._get_provider_config("chatgpt-5")

        assert "not configured" in str(exc_info.value)

    @patch('api.llm_client.get_config')
    def test_get_fallback_provider(self, mock_get_config, mock_config_grok):
        """Test getting fallback provider."""
        mock_get_config.return_value = mock_config_grok
        client = LLMClient()

        # Grok-4 fallback is ChatGPT-5
        fallback = client._get_fallback_provider("grok-4")
        assert fallback == "chatgpt-5"

        # ChatGPT-5 fallback is Grok-4
        fallback = client._get_fallback_provider("chatgpt-5")
        assert fallback == "grok-4"


class TestChatCompletion:
    """Test chat completion with provider calls (AC #1, #2)."""

    @pytest.mark.asyncio
    @patch('api.llm_client.get_config')
    async def test_chat_completion_success_grok(self, mock_get_config, mock_config_grok):
        """Test successful chat completion with Grok-4."""
        mock_get_config.return_value = mock_config_grok

        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello!"}}],
            "usage": {"total_tokens": 10}
        }

        with patch.object(httpx.AsyncClient, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            async with LLMClient() as client:
                messages = [{"role": "user", "content": "Hi"}]
                result = await client.chat_completion(messages)

                assert "choices" in result
                assert result["choices"][0]["message"]["content"] == "Hello!"
                mock_post.assert_called_once()

    @pytest.mark.asyncio
    @patch('api.llm_client.get_config')
    async def test_chat_completion_success_chatgpt(self, mock_get_config, mock_config_chatgpt):
        """Test successful chat completion with ChatGPT-5."""
        mock_get_config.return_value = mock_config_chatgpt

        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello from ChatGPT!"}}]
        }

        with patch.object(httpx.AsyncClient, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            async with LLMClient() as client:
                messages = [{"role": "user", "content": "Hi"}]
                result = await client.chat_completion(messages)

                assert result["choices"][0]["message"]["content"] == "Hello from ChatGPT!"


class TestProviderFailover:
    """Test automatic provider failover (AC #3)."""

    @pytest.mark.asyncio
    @patch('api.llm_client.get_config')
    async def test_failover_on_timeout(self, mock_get_config, mock_config_grok):
        """Test failover when Grok-4 times out."""
        mock_get_config.return_value = mock_config_grok

        # First call (Grok-4) times out, second call (ChatGPT-5) succeeds
        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {
            "choices": [{"message": {"content": "Fallback response"}}]
        }

        call_count = 0

        async def mock_post_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call (Grok-4) times out
                raise httpx.TimeoutException("Timeout")
            else:
                # Second call (ChatGPT-5) succeeds
                return mock_response_success

        with patch.object(httpx.AsyncClient, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = mock_post_side_effect

            async with LLMClient() as client:
                messages = [{"role": "user", "content": "Hi"}]
                result = await client.chat_completion(messages)

                # Should get fallback response
                assert result["choices"][0]["message"]["content"] == "Fallback response"
                # Should have called post twice (primary + fallback)
                assert call_count == 2

    @pytest.mark.asyncio
    @patch('api.llm_client.get_config')
    async def test_failover_on_network_error(self, mock_get_config, mock_config_grok):
        """Test failover on network error."""
        mock_get_config.return_value = mock_config_grok

        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {
            "choices": [{"message": {"content": "Fallback response"}}]
        }

        call_count = 0

        async def mock_post_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.NetworkError("Connection refused")
            else:
                return mock_response_success

        with patch.object(httpx.AsyncClient, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = mock_post_side_effect

            async with LLMClient() as client:
                messages = [{"role": "user", "content": "Hi"}]
                result = await client.chat_completion(messages)

                assert result["choices"][0]["message"]["content"] == "Fallback response"
                assert call_count == 2

    @pytest.mark.asyncio
    @patch('api.llm_client.get_config')
    async def test_failover_on_api_error(self, mock_get_config, mock_config_grok):
        """Test failover on API error (500)."""
        mock_get_config.return_value = mock_config_grok

        mock_response_error = Mock()
        mock_response_error.status_code = 500
        mock_response_error.json.return_value = {
            "error": {"message": "Internal server error"}
        }

        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {
            "choices": [{"message": {"content": "Fallback response"}}]
        }

        call_count = 0

        async def mock_post_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_response_error
            else:
                return mock_response_success

        with patch.object(httpx.AsyncClient, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = mock_post_side_effect

            async with LLMClient() as client:
                messages = [{"role": "user", "content": "Hi"}]
                result = await client.chat_completion(messages)

                assert result["choices"][0]["message"]["content"] == "Fallback response"
                assert call_count == 2


class TestBothProvidersFailing:
    """Test error handling when both providers fail (AC #4, #5)."""

    @pytest.mark.asyncio
    @patch('api.llm_client.get_config')
    async def test_both_providers_fail(self, mock_get_config, mock_config_grok):
        """Test user-friendly error when both providers fail."""
        mock_get_config.return_value = mock_config_grok

        # Both calls fail
        with patch.object(httpx.AsyncClient, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Timeout")

            async with LLMClient() as client:
                messages = [{"role": "user", "content": "Hi"}]

                with pytest.raises(LLMClientError) as exc_info:
                    await client.chat_completion(messages)

                # Should have user-friendly error message
                assert "technical difficulties" in str(exc_info.value).lower()
                assert "try again" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    @patch('api.llm_client.get_config')
    async def test_no_fallback_available(self, mock_get_config, mock_config_grok_only):
        """Test error when no fallback provider is available."""
        mock_get_config.return_value = mock_config_grok_only

        with patch.object(httpx.AsyncClient, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Timeout")

            async with LLMClient() as client:
                messages = [{"role": "user", "content": "Hi"}]

                with pytest.raises(LLMClientError) as exc_info:
                    await client.chat_completion(messages)

                # Should have user-friendly error message
                assert "technical difficulties" in str(exc_info.value).lower()


class TestRateLimiting:
    """Test rate limiting and retry-after handling (AC #6)."""

    @pytest.mark.asyncio
    @patch('api.llm_client.get_config')
    async def test_rate_limit_detection(self, mock_get_config, mock_config_grok):
        """Test rate limit detection and failover."""
        mock_get_config.return_value = mock_config_grok

        # First call hits rate limit, second succeeds
        mock_response_rate_limit = Mock()
        mock_response_rate_limit.status_code = 429
        mock_response_rate_limit.headers = {"retry-after": "60"}
        mock_response_rate_limit.json.return_value = {}

        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {
            "choices": [{"message": {"content": "Success after rate limit"}}]
        }

        call_count = 0

        async def mock_post_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_response_rate_limit
            else:
                return mock_response_success

        with patch.object(httpx.AsyncClient, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = mock_post_side_effect

            async with LLMClient() as client:
                messages = [{"role": "user", "content": "Hi"}]
                result = await client.chat_completion(messages)

                # Should fallback and succeed
                assert result["choices"][0]["message"]["content"] == "Success after rate limit"

    @pytest.mark.asyncio
    @patch('api.llm_client.get_config')
    async def test_rate_limit_both_providers(self, mock_get_config, mock_config_grok):
        """Test error when both providers hit rate limit."""
        mock_get_config.return_value = mock_config_grok

        mock_response_rate_limit = Mock()
        mock_response_rate_limit.status_code = 429
        mock_response_rate_limit.headers = {"retry-after": "60"}
        mock_response_rate_limit.json.return_value = {}

        with patch.object(httpx.AsyncClient, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response_rate_limit

            async with LLMClient() as client:
                messages = [{"role": "user", "content": "Hi"}]

                with pytest.raises(LLMClientError) as exc_info:
                    await client.chat_completion(messages)

                # Should have user-friendly error message
                assert "technical difficulties" in str(exc_info.value).lower()


class TestHealthCheck:
    """Test health check functionality (AC #1, #2)."""

    @patch('api.llm_client.get_config')
    def test_health_check_ok(self, mock_get_config, mock_config_grok):
        """Test health check returns 'ok' when primary provider is available."""
        mock_get_config.return_value = mock_config_grok
        client = LLMClient()

        status = client.health_check()

        assert status == "ok"

    @patch('api.llm_client.get_config')
    def test_health_check_degraded(self, mock_get_config, mock_config_grok_only):
        """Test health check returns 'degraded' when only fallback available."""
        # Configure with ChatGPT primary but only ChatGPT available
        config = {
            "LLM_PROVIDER": "grok-4",
            "GROK_API_KEY": None,
            "CHATGPT_API_KEY": "test-key"
        }
        mock_get_config.return_value = config
        client = LLMClient()

        status = client.health_check()

        assert status == "degraded"

    @patch('api.llm_client.get_config')
    def test_health_check_unavailable(self, mock_get_config):
        """Test health check returns 'unavailable' when no providers available."""
        config = {
            "LLM_PROVIDER": "grok-4",
            "GROK_API_KEY": None,
            "CHATGPT_API_KEY": None
        }
        mock_get_config.return_value = config
        client = LLMClient()

        status = client.health_check()

        assert status == "unavailable"


class TestErrorLogging:
    """Test structured error logging (AC #5)."""

    @pytest.mark.asyncio
    @patch('api.llm_client.get_config')
    @patch('api.llm_client.logger')
    async def test_provider_failure_logged(self, mock_logger, mock_get_config, mock_config_grok):
        """Test that provider failures are logged with details."""
        mock_get_config.return_value = mock_config_grok

        with patch.object(httpx.AsyncClient, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Timeout")

            async with LLMClient() as client:
                messages = [{"role": "user", "content": "Hi"}]

                try:
                    await client.chat_completion(messages)
                except LLMClientError:
                    pass  # Expected

                # Verify logging was called for failures
                assert mock_logger.warning.called or mock_logger.error.called

    @pytest.mark.asyncio
    @patch('api.llm_client.get_config')
    @patch('api.llm_client.logger')
    async def test_failover_logged(self, mock_logger, mock_get_config, mock_config_grok):
        """Test that failover attempts are logged."""
        mock_get_config.return_value = mock_config_grok

        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {
            "choices": [{"message": {"content": "Success"}}]
        }

        call_count = 0

        async def mock_post_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.TimeoutException("Timeout")
            else:
                return mock_response_success

        with patch.object(httpx.AsyncClient, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = mock_post_side_effect

            async with LLMClient() as client:
                messages = [{"role": "user", "content": "Hi"}]
                await client.chat_completion(messages)

                # Verify failover was logged
                warning_calls = [call for call in mock_logger.warning.call_args_list]
                assert any("fallback" in str(call).lower() for call in warning_calls)
